"""Request / response models (Pydantic)."""
from pydantic import BaseModel, ConfigDict, Field, field_validator


class FareRequest(BaseModel):
    """What the rider sends. Everything else (distance, weather, time, surge...)
    is computed by the backend, so extra fields are rejected."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source: str = Field(min_length=1, max_length=100, examples=["Beacon Hill"])
    destination: str = Field(min_length=1, max_length=100, examples=["Financial District"])
    cab_type: str = Field(min_length=1, max_length=20, examples=["Uber"])
    name: str = Field(min_length=1, max_length=40, examples=["UberX"])

    @field_validator("source", "destination", "cab_type", "name")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class WeatherSummary(BaseModel):
    temperature_f: float
    cloud_cover_pct: float
    humidity_pct: float
    wind_mph: float
    pressure_mb: float
    raining: bool


class Coordinates(BaseModel):
    latitude: float
    longitude: float


class FareResponse(BaseModel):
    estimated_fare: float
    currency: str = "USD"
    source: str
    destination: str
    cab_type: str
    name: str
    distance: float
    distance_unit: str = "miles"
    duration: float
    duration_unit: str = "minutes"
    surge_multiplier: float
    demand_score: float
    weather: WeatherSummary
    source_coordinates: Coordinates
    destination_coordinates: Coordinates
    timestamp: str
    disclaimer: str = (
        "Prototype estimate from a model trained on a historical Boston ride dataset. "
        "The surge multiplier comes from a simulated demand model, not from real "
        "Uber/Lyft pricing."
    )


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    detail: str | None = None


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody


# =====================================================================================
# Exact-coordinate API  (POST /api/v2/fare/predict, GET /api/v1/locations/search|reverse)
# =====================================================================================
class GeoPoint(BaseModel):
    """A real point chosen by the rider (search result or map click)."""

    model_config = ConfigDict(extra="forbid")

    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False, examples=[42.35])
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False, examples=[-71.0773])
    display_name: str | None = Field(
        default=None,
        max_length=300,
        description="Optional label (e.g. from /locations/search). Echoed back, never used for pricing.",
        examples=["Copley Square, Back Bay, Boston, MA"],
    )

    @field_validator("display_name")
    @classmethod
    def blank_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = " ".join(value.split())
        return value or None


class ExactFareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    pickup: GeoPoint
    destination: GeoPoint
    cab_type: str = Field(min_length=1, max_length=20, examples=["Uber"])
    name: str = Field(min_length=1, max_length=40, examples=["UberX"], description="Ride option")

    @field_validator("cab_type", "name")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class PlaceInfo(BaseModel):
    """One end of the trip: the REAL point + the model category it was mapped to."""

    latitude: float
    longitude: float
    display_name: str | None = None
    neighborhood: str | None = Field(
        default=None, description="Official City of Boston neighbourhood containing the point."
    )
    model_area: str = Field(description="Category sent to the ML model (one of the 12 it knows).")


class RouteInfo(BaseModel):
    distance: float
    distance_unit: str = "miles"
    duration: float
    duration_unit: str = "minutes"
    geometry: dict = Field(
        description='GeoJSON LineString: {"type":"LineString","coordinates":[[lon,lat],...]}'
    )


class WeatherInfo(WeatherSummary):
    rain_inches: float = Field(description="Rain in the last hour, inches (0.0 when dry).")


class ExactFareResponse(BaseModel):
    estimated_fare: float
    currency: str = "USD"
    cab_type: str
    name: str
    pickup: PlaceInfo
    destination: PlaceInfo
    route: RouteInfo
    surge_multiplier: float
    demand_score: float
    weather: WeatherInfo
    timestamp: str = Field(description="Boston local time, ISO 8601 with UTC offset.")
    timezone: str = "America/New_York"
    disclaimer: str = (
        "Prototype estimate from a model trained on a historical Boston ride dataset. "
        "The surge multiplier comes from a simulated demand model, not from real "
        "Uber/Lyft pricing."
    )


class PlaceResult(BaseModel):
    display_name: str
    name: str
    latitude: float
    longitude: float
    neighborhood: str | None = None
    model_area: str | None = Field(
        default=None, description="Model category for this point, or null if the model can't price it."
    )
    supported: bool = Field(description="True when a fare can be predicted for this point.")


class LocationSearchResponse(BaseModel):
    query: str
    results: list[PlaceResult]
    attribution: str


class ReverseGeocodeResponse(PlaceResult):
    message: str | None = Field(
        default=None, description="Why the point is unsupported (only when supported=false)."
    )
    attribution: str
