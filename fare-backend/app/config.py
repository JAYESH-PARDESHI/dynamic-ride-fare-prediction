"""Application settings, loaded from environment variables / the .env file."""
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- general ---
    app_env: Literal["development", "production"] = "development"
    log_level: str = "INFO"

    # --- ML model ---
    model_path: str = "models/fare_prediction_pipeline.pkl"

    # --- routing (distance + duration) ---
    routing_provider: Literal["osrm", "openrouteservice"] = "osrm"
    routing_api_key: SecretStr | None = None  # only needed for openrouteservice
    routing_base_url: str | None = None  # optional override (e.g. self-hosted OSRM)

    # --- weather ---
    weather_provider: Literal["openmeteo", "openweathermap"] = "openmeteo"
    weather_api_key: SecretStr | None = None  # only needed for openweathermap
    weather_base_url: str | None = None  # optional override
    weather_cache_seconds: int = 600

    # --- geocoding (location search + reverse geocoding) ---
    # Default provider: public Nominatim (OpenStreetMap). Its usage policy requires an
    # identifying User-Agent, max 1 request/second and caching - all enforced in
    # app/services/geocoding_service.py. For production traffic use your own Nominatim
    # instance or a commercial provider and set GEOCODER_BASE_URL.
    geocoder_base_url: str = "https://nominatim.openstreetmap.org"
    geocoder_contact: str = ""  # email or URL put into the User-Agent (strongly recommended)
    geocoder_min_interval_seconds: float = 1.0  # provider policy: <= 1 request / second
    geocoder_max_queue_seconds: float = 4.0  # waiting longer than this -> HTTP 429
    geocoder_cache_seconds: int = 24 * 3600
    geocoder_result_limit: int = 8

    # --- ML time features ---
    # "utc"    : date_time sent to the model is UTC (what the pickle was trained on).
    # "boston" : date_time sent to the model is Boston local wall-clock time.
    # See README "Boston local time" before changing this.
    model_clock: Literal["utc", "boston"] = "utc"

    # --- HTTP client ---
    http_timeout_seconds: float = 8.0

    # --- surge simulation ---
    # Which cab types get the simulated surge. Other cab types are sent to the
    # model with surge_multiplier = 1.0. See README ("Surge simulation").
    surge_cab_types: str = "Uber,Lyft"

    # --- CORS (comma separated list of origins) ---
    cors_allowed_origins: str = "http://localhost:3000,http://localhost:5173"

    @property
    def resolved_model_path(self) -> Path:
        path = Path(self.model_path)
        return path if path.is_absolute() else BASE_DIR / path

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    @property
    def surge_cab_types_set(self) -> set[str]:
        return {c.strip().lower() for c in self.surge_cab_types.split(",") if c.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
