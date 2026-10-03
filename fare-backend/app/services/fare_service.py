"""Orchestrates one fare prediction. Business logic lives here, not in main.py."""
import asyncio
import logging
from datetime import datetime
import math
from typing import Callable

import pandas as pd
from sklearn.pipeline import Pipeline

from app.catalog import Location, ModelCatalog
from app.config import Settings
from app.errors import (
    InvalidRequestError,
    PredictionError,
    SameModelAreaError,
)
from app.schemas import (
    Coordinates,
    ExactFareRequest,
    ExactFareResponse,
    FareRequest,
    FareResponse,
    PlaceInfo,
    RouteInfo,
    WeatherInfo,
    WeatherSummary,
)
from app.services.location_mapping_service import LocationMappingService
from app.services.demand_service import (
    ALLOWED_SURGE_VALUES,
    calculate_demand_score,
    calculate_surge_multiplier,
)
from app.services.routing_service import Route, RoutingService
from app.services.weather_service import Weather, WeatherService
from app.utils.time_features import to_boston, to_model_clock, utc_now

logger = logging.getLogger(__name__)

# Exactly the raw columns (and order) the pipeline was fitted on.
# Confirmed from the notebook: x_train.columns == these 14.
MODEL_INPUT_COLUMNS = [
    "distance", "cab_type", "destination", "source", "surge_multiplier", "name",
    "date_time", "hour_date", "temp", "clouds", "pressure", "rain", "humidity", "wind",
]


def build_model_input(
    *,
    route: Route,
    weather: Weather,
    source: Location,
    destination: Location,
    cab_type: str,
    ride_name: str,
    surge_multiplier: float,
    now_utc: datetime,
    model_clock: str = "utc",
) -> pd.DataFrame:
    """One-row DataFrame of RAW columns. The pipeline does all encoding/scaling."""
    date_time, hour_date = to_model_clock(now_utc, model_clock)
    row = {
        "distance": route.distance,
        "cab_type": cab_type,
        "destination": destination.name,
        "source": source.name,
        "surge_multiplier": surge_multiplier,
        "name": ride_name,
        "date_time": date_time,
        "hour_date": hour_date,
        **weather.to_model_dict(),
    }
    frame = pd.DataFrame([row], columns=MODEL_INPUT_COLUMNS)
    # Match the training dtypes (float columns must be float even if a value is NaN).
    float_cols = ["distance", "surge_multiplier", "temp", "clouds", "pressure",
                  "rain", "humidity", "wind"]
    frame[float_cols] = frame[float_cols].astype("float64")
    return frame


SAME_POINT_METERS = 25.0  # pickup/destination closer than this count as "the same point"


def _distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle (haversine) distance - only used for the "same point" check."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class FareService:
    def __init__(
        self,
        pipeline: Pipeline,
        catalog: ModelCatalog,
        routing: RoutingService,
        weather: WeatherService,
        settings: Settings,
        clock: Callable[[], datetime] = utc_now,
        mapper: LocationMappingService | None = None,
    ):
        self._mapper = mapper
        self._pipeline = pipeline
        self._catalog = catalog
        self._routing = routing
        self._weather = weather
        self._settings = settings
        self._clock = clock

    async def predict_fare(self, request: FareRequest) -> FareResponse:
        now_utc = self._clock()

        # 1. Validate (strict - nothing is guessed or mapped to a "closest" place)
        source = self._catalog.resolve_location(request.source, "source")
        destination = self._catalog.resolve_location(request.destination, "destination")
        if source.name == destination.name:
            raise InvalidRequestError("Source and destination must be different locations.")
        cab_type, ride_name = self._catalog.validate_ride_option(request.cab_type, request.name)

        # 2-5. Route and weather are independent -> fetch them at the same time
        route, weather = await asyncio.gather(
            self._routing.get_route(source, destination),
            self._weather.get_current_weather(source.latitude, source.longitude),
        )

        # 6-8. Simulated demand (Boston local time) -> discrete surge multiplier
        local_time = to_boston(now_utc)
        demand_score = calculate_demand_score(local_time, source.name, destination.name)
        if cab_type.lower() in self._settings.surge_cab_types_set:
            surge = calculate_surge_multiplier(demand_score)
        else:
            surge = 1.0
        if surge not in ALLOWED_SURGE_VALUES:  # safety net - should be impossible
            raise PredictionError("Internal error while selecting the surge multiplier.")
        logger.info(
            "Demand score %.3f -> surge %.2f (%s, local %s)",
            demand_score, surge, cab_type, local_time.strftime("%a %H:%M"),
        )

        # 9-10. Build raw input and run the EXISTING pipeline (in a worker thread,
        # because predict() is CPU-bound and must not block the event loop)
        frame = build_model_input(
            route=route, weather=weather, source=source, destination=destination,
            cab_type=cab_type, ride_name=ride_name, surge_multiplier=surge, now_utc=now_utc,
            model_clock=self._settings.model_clock,
        )
        raw_fare = await asyncio.to_thread(self._predict, frame)
        fare = round(max(raw_fare, 0.0), 2)
        logger.info("Prediction complete: raw=%.4f displayed=%.2f", raw_fare, fare)

        return FareResponse(
            estimated_fare=fare,
            source=source.name,
            destination=destination.name,
            cab_type=cab_type,
            name=ride_name,
            distance=route.distance,
            duration=route.duration,
            surge_multiplier=surge,
            demand_score=demand_score,
            weather=WeatherSummary(
                temperature_f=round(weather.temp, 1),
                cloud_cover_pct=round(weather.clouds * 100),
                humidity_pct=round(weather.humidity * 100),
                wind_mph=round(weather.wind, 1),
                pressure_mb=round(weather.pressure, 1),
                raining=weather.rain is not None,
            ),
            source_coordinates=Coordinates(
                latitude=route.source_coordinates[0], longitude=route.source_coordinates[1]
            ),
            destination_coordinates=Coordinates(
                latitude=route.destination_coordinates[0],
                longitude=route.destination_coordinates[1],
            ),
            timestamp=now_utc.isoformat(timespec="seconds"),
        )

    # ------------------------------------------------------------------------------
    # Exact-coordinate flow (POST /api/v2/fare/predict)
    # ------------------------------------------------------------------------------
    async def predict_exact(self, request: ExactFareRequest) -> ExactFareResponse:
        """Real coordinates -> model areas; exact coordinates -> OSRM + weather."""
        if self._mapper is None:
            raise PredictionError("Location mapping is not available on the server.")
        now_utc = self._clock()
        pu, do = request.pickup, request.destination

        # 1. Validate: ride option, service area, model-area mapping (strict, nothing guessed)
        cab_type, ride_name = self._catalog.validate_ride_option(request.cab_type, request.name)
        if _distance_meters(pu.latitude, pu.longitude, do.latitude, do.longitude) < SAME_POINT_METERS:
            raise InvalidRequestError("Pickup and destination must be different locations.")
        pu_match = self._mapper.require_model_area(pu.latitude, pu.longitude, "pickup location")
        do_match = self._mapper.require_model_area(do.latitude, do.longitude, "destination")
        # The mapped category must also be one the loaded pickle was trained on.
        source_name = self._catalog.resolve_location(pu_match.model_area, "source").name
        dest_name = self._catalog.resolve_location(do_match.model_area, "destination").name
        if source_name == dest_name:
            raise SameModelAreaError(
                f"Pickup and destination are both in the '{source_name}' model area. The fare "
                "model was trained on trips between different areas, so it cannot price this trip."
            )

        # 2. EXACT coordinates (not neighbourhood centres) go to routing and weather.
        source = Location(source_name, pu.latitude, pu.longitude)
        destination = Location(dest_name, do.latitude, do.longitude)
        route, weather = await asyncio.gather(
            self._routing.get_route(source, destination, include_geometry=True),
            self._weather.get_current_weather(pu.latitude, pu.longitude),
        )
        if route.geometry is None:
            raise PredictionError("The route geometry is missing.")

        # 3. Boston local time -> simulated demand/surge (model categories, as trained)
        local_time = to_boston(now_utc)
        demand_score = calculate_demand_score(local_time, source_name, dest_name)
        surge = (
            calculate_surge_multiplier(demand_score)
            if cab_type.lower() in self._settings.surge_cab_types_set
            else 1.0
        )
        if surge not in ALLOWED_SURGE_VALUES:
            raise PredictionError("Internal error while selecting the surge multiplier.")

        # 4. The existing 14 raw model columns -> existing pipeline
        frame = build_model_input(
            route=route, weather=weather, source=source, destination=destination,
            cab_type=cab_type, ride_name=ride_name, surge_multiplier=surge, now_utc=now_utc,
            model_clock=self._settings.model_clock,
        )
        raw_fare = await asyncio.to_thread(self._predict, frame)
        fare = round(max(raw_fare, 0.0), 2)
        logger.info(
            "Exact prediction %s -> %s: raw=%.4f displayed=%.2f surge=%.2f (local %s)",
            source_name, dest_name, raw_fare, fare, surge, local_time.strftime("%a %H:%M"),
        )

        return ExactFareResponse(
            estimated_fare=fare,
            cab_type=cab_type,
            name=ride_name,
            pickup=PlaceInfo(
                latitude=pu.latitude, longitude=pu.longitude, display_name=pu.display_name,
                neighborhood=pu_match.neighborhood, model_area=source_name,
            ),
            destination=PlaceInfo(
                latitude=do.latitude, longitude=do.longitude, display_name=do.display_name,
                neighborhood=do_match.neighborhood, model_area=dest_name,
            ),
            route=RouteInfo(distance=route.distance, duration=route.duration, geometry=route.geometry),
            surge_multiplier=surge,
            demand_score=demand_score,
            weather=WeatherInfo(
                temperature_f=round(weather.temp, 1),
                cloud_cover_pct=round(weather.clouds * 100),
                humidity_pct=round(weather.humidity * 100),
                wind_mph=round(weather.wind, 1),
                pressure_mb=round(weather.pressure, 1),
                raining=weather.rain is not None,
                rain_inches=round(weather.rain, 3) if weather.rain is not None else 0.0,
            ),
            timestamp=local_time.isoformat(timespec="seconds"),
        )

    def _predict(self, frame: pd.DataFrame) -> float:
        try:
            prediction = self._pipeline.predict(frame)
            return float(prediction[0])
        except Exception as exc:
            # Full details go to the server log only - never to the client.
            logger.exception("Pipeline prediction failed")
            raise PredictionError("The fare could not be predicted. Please try again later.") from exc
