"""FastAPI app: wiring, routes, error handlers. Business logic is in app/services/."""
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.catalog import ModelCatalog
from app.config import Settings, get_settings
from app.errors import (
    AppError,
    ModelLoadError,
    ModelUnavailableError,
    OutsideServiceAreaError,
)
from app.model_loader import load_pipeline
from app.schemas import (
    ErrorResponse,
    ExactFareRequest,
    ExactFareResponse,
    FareRequest,
    FareResponse,
    HealthResponse,
    LocationSearchResponse,
    PlaceResult,
    ReverseGeocodeResponse,
)
from app.services.fare_service import FareService
from app.services.geocoding_service import ATTRIBUTION, GeocodingService, Place
from app.services.location_mapping_service import LocationMappingService
from app.services.routing_service import RoutingService
from app.services.weather_service import WeatherService

logger = logging.getLogger("app")


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    # httpx logs full request URLs at INFO - that would put API keys in the logs.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.fare_service = None
        app.state.catalog = None
        app.state.model_error = None
        app.state.mapper = None
        app.state.geocoder = None

        # Load the model ONCE. If it fails, keep the server up so /health can say why.
        try:
            pipeline = load_pipeline(settings.resolved_model_path)
            catalog = ModelCatalog.from_pipeline(pipeline)
        except ModelLoadError as exc:
            app.state.model_error = str(exc)
            logger.error("MODEL LOADING FAILED: %s", exc)
            pipeline = catalog = None

        # Boundary data is shipped with the code (app/data) -> fail fast if it is broken.
        supported = (set(catalog.sources) & set(catalog.destinations)) if catalog else None
        mapper = LocationMappingService.from_data_dir(supported_areas=supported)
        app.state.mapper = mapper

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(settings.http_timeout_seconds),
            headers={"User-Agent": "fare-prediction-backend/1.0"},
        ) as client:
            # Location search / reverse geocoding work even if the model failed to load.
            app.state.geocoder = GeocodingService(client, settings, mapper)
            if pipeline is not None:
                app.state.catalog = catalog
                app.state.fare_service = FareService(
                    pipeline=pipeline,
                    catalog=catalog,
                    routing=RoutingService(client, settings),
                    weather=WeatherService(client, settings),
                    settings=settings,
                    mapper=mapper,
                )
                logger.info("Startup complete - model ready.")
            yield

    app = FastAPI(
        title="Dynamic Ride Fare Prediction API",
        version="1.0.0",
        description="Backend around a pre-trained XGBoost fare pipeline. "
        "Prototype: trained on a Boston dataset; surge is simulated.",
        lifespan=lifespan,
    )

    # ---- CORS (origins come from CORS_ALLOWED_ORIGINS) ----
    origins = settings.cors_origins_list
    if "*" in origins and settings.app_env == "production":
        logger.warning("CORS_ALLOWED_ORIGINS='*' in production - restrict this to your frontend URL.")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    # ---- error handlers: clean JSON, no stack traces ----
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError):
        logger.warning("%s: %s", exc.code, exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        problems = [
            f"{'.'.join(str(p) for p in e['loc'] if p != 'body')}: {e['msg']}"
            for e in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "invalid_request", "message": "; ".join(problems)}},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception):
        logger.exception("Unhandled error")
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error", "message": "Something went wrong."}},
        )

    # ---- dependencies ----
    def get_fare_service(request: Request) -> FareService:
        service = request.app.state.fare_service
        if service is None:
            raise ModelUnavailableError(
                "The fare model is not loaded on the server. Check the server logs / GET /health."
            )
        return service

    def get_geocoder(request: Request) -> GeocodingService:
        return request.app.state.geocoder

    def get_mapper(request: Request) -> LocationMappingService:
        return request.app.state.mapper

    app.state.get_fare_service = get_fare_service  # handy for tests (dependency_overrides)
    app.state.get_geocoder = get_geocoder
    app.state.get_mapper = get_mapper

    def to_place_result(place: Place) -> PlaceResult:
        return PlaceResult(
            display_name=place.display_name,
            name=place.name,
            latitude=place.latitude,
            longitude=place.longitude,
            neighborhood=place.area.neighborhood,
            model_area=place.area.model_area,
            supported=place.area.model_area is not None,
        )

    # ---- routes ----
    @app.get("/health", response_model=HealthResponse)
    async def health(request: Request):
        if request.app.state.fare_service is None:
            return JSONResponse(
                status_code=503,
                content=HealthResponse(
                    status="degraded", model_loaded=False, detail=request.app.state.model_error
                ).model_dump(),
            )
        return HealthResponse(status="ok", model_loaded=True)

    @app.get("/api/v1/locations")
    async def locations(request: Request):
        """What the trained model supports (useful for a frontend dropdown)."""
        catalog = request.app.state.catalog
        if catalog is None:
            raise ModelUnavailableError("The fare model is not loaded on the server.")
        return catalog.describe()

    @app.get(
        "/api/v1/locations/search",
        response_model=LocationSearchResponse,
        summary="Search real places in Boston",
        responses={422: {"model": ErrorResponse}, 429: {"model": ErrorResponse},
                   502: {"model": ErrorResponse}, 504: {"model": ErrorResponse}},
    )
    async def search_locations(
        q: str = Query(..., description="Place or address text, e.g. 'Copley Square'", max_length=200),
        geocoder: GeocodingService = Depends(get_geocoder),
    ):
        places = await geocoder.search(q)
        return LocationSearchResponse(
            query=" ".join(q.split()),
            results=[to_place_result(p) for p in places],
            attribution=ATTRIBUTION,
        )

    @app.get(
        "/api/v1/locations/reverse",
        response_model=ReverseGeocodeResponse,
        summary="Name for a point clicked on the map",
        responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse},
                   429: {"model": ErrorResponse}, 502: {"model": ErrorResponse},
                   504: {"model": ErrorResponse}},
    )
    async def reverse_geocode(
        latitude: float = Query(..., ge=-90, le=90, allow_inf_nan=False),
        longitude: float = Query(..., ge=-180, le=180, allow_inf_nan=False),
        geocoder: GeocodingService = Depends(get_geocoder),
        mapper: LocationMappingService = Depends(get_mapper),
    ):
        # Cheap local check first: no provider call for points outside Boston.
        if not mapper.in_service_area(latitude, longitude):
            raise OutsideServiceAreaError("That point is outside the supported Boston service area.")
        place = await geocoder.reverse(latitude, longitude)
        result = to_place_result(place)
        message = None
        if not result.supported:
            message = (
                f"This location is in {result.neighborhood}, which the fare model does not cover."
            )
        return ReverseGeocodeResponse(**result.model_dump(), message=message, attribution=ATTRIBUTION)

    @app.post(
        "/api/v2/fare/predict",
        response_model=ExactFareResponse,
        summary="Predict a fare from exact pickup / destination coordinates (recommended)",
        responses={
            422: {"model": ErrorResponse},
            502: {"model": ErrorResponse},
            503: {"model": ErrorResponse},
            504: {"model": ErrorResponse},
        },
    )
    async def predict_fare_exact(
        body: ExactFareRequest, service: FareService = Depends(get_fare_service)
    ):
        logger.info(
            "Exact fare request: (%.5f,%.5f) -> (%.5f,%.5f) (%s / %s)",
            body.pickup.latitude, body.pickup.longitude,
            body.destination.latitude, body.destination.longitude,
            body.cab_type, body.name,
        )
        return await service.predict_exact(body)

    @app.post(
        "/api/v1/fare/predict",
        response_model=FareResponse,
        deprecated=True,
        summary="[Deprecated] Predict from model category names - use /api/v2/fare/predict",
        responses={
            422: {"model": ErrorResponse},
            502: {"model": ErrorResponse},
            503: {"model": ErrorResponse},
            504: {"model": ErrorResponse},
        },
    )
    async def predict_fare(
        body: FareRequest, response: Response, service: FareService = Depends(get_fare_service)
    ):
        # Still works exactly as before, but new clients should use the v2 endpoint.
        response.headers["Deprecation"] = "true"
        response.headers["Link"] = '</api/v2/fare/predict>; rel="successor-version"'
        logger.info(
            "Fare request: %s -> %s (%s / %s)", body.source, body.destination, body.cab_type, body.name
        )
        return await service.predict_fare(body)

    return app


app = create_app()
