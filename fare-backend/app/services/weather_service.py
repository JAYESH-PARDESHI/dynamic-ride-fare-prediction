"""Current weather, converted to the UNITS THE MODEL WAS TRAINED ON.

Training data (weather.csv), judging by the value ranges in the notebook:
    temp      degrees Fahrenheit   (min 19.6, mean 39.2 in the training rows)
    clouds    fraction 0-1
    pressure  millibar / hPa       (~988 - 1022)
    humidity  fraction 0-1
    wind      miles per hour
    rain      inches in the last hour; MISSING (NaN) when it was not raining
              (82% of rows) - the pipeline imputes 0 and adds a "missing" flag

Providers (set WEATHER_PROVIDER in .env):
  openmeteo       - default, no API key needed.
  openweathermap  - needs WEATHER_API_KEY.

Weather is fetched for the SOURCE location (training weather was joined on source).
"""

import asyncio
import logging
from dataclasses import dataclass

import httpx

from app.config import Settings
from app.errors import (
    ConfigurationError,
    ExternalServiceError,
    ExternalTimeoutError,
)
from app.utils.cache import TTLCache

logger = logging.getLogger(__name__)

MM_PER_INCH = 25.4
DEFAULT_OPENMETEO_URL = "https://api.open-meteo.com"
DEFAULT_OWM_URL = "https://api.openweathermap.org"


@dataclass(frozen=True)
class Weather:
    temp: float  # deg F
    clouds: float  # 0-1
    pressure: float  # mb / hPa
    humidity: float  # 0-1
    wind: float  # mph
    rain: float | None  # inches in last hour, None when not raining

    def to_model_dict(self) -> dict:
        """The raw weather columns the pipeline expects (rain None -> NaN)."""
        return {
            "temp": self.temp,
            "clouds": self.clouds,
            "pressure": self.pressure,
            "humidity": self.humidity,
            "wind": self.wind,
            "rain": float("nan") if self.rain is None else self.rain,
        }


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


class WeatherService:
    def __init__(self, client: httpx.AsyncClient, settings: Settings):
        self._client = client
        self._provider = settings.weather_provider
        self._api_key = settings.weather_api_key
        self._base_url = (
            settings.weather_base_url
            or (
                DEFAULT_OPENMETEO_URL
                if self._provider == "openmeteo"
                else DEFAULT_OWM_URL
            )
        ).rstrip("/")

        self._cache: TTLCache[Weather] = TTLCache(
            ttl_seconds=settings.weather_cache_seconds
        )

    async def get_current_weather(
        self,
        latitude: float,
        longitude: float,
    ) -> Weather:
        # Round coordinates so nearby requests reuse the same weather result.
        key = (round(latitude, 3), round(longitude, 3))

        cached = self._cache.get(key)
        if cached is not None:
            logger.info("Weather cache hit: %s", key)
            return cached

        if self._provider == "openmeteo":
            weather = await self._openmeteo(latitude, longitude)
        else:
            weather = await self._openweathermap(latitude, longitude)

        logger.info(
            "Weather: temp=%.1fF clouds=%.2f pressure=%.1f "
            "humidity=%.2f wind=%.1fmph rain=%s (%s)",
            weather.temp,
            weather.clouds,
            weather.pressure,
            weather.humidity,
            weather.wind,
            weather.rain,
            self._provider,
        )

        self._cache.set(key, weather)
        return weather

    # ----------------------------------------------------------- Open-Meteo

    async def _openmeteo(self, lat: float, lon: float) -> Weather:
        data = await self._get(
            f"{self._base_url}/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current": (
                    "temperature_2m,relative_humidity_2m,cloud_cover,"
                    "pressure_msl,wind_speed_10m,rain"
                ),
                "temperature_unit": "fahrenheit",
                "wind_speed_unit": "mph",
                "precipitation_unit": "inch",
            },
        )

        try:
            cur = data["current"]
            rain = cur.get("rain")

            return Weather(
                temp=float(cur["temperature_2m"]),
                clouds=_clamp01(float(cur["cloud_cover"]) / 100),
                pressure=float(cur["pressure_msl"]),
                humidity=_clamp01(
                    float(cur["relative_humidity_2m"]) / 100
                ),
                wind=float(cur["wind_speed_10m"]),
                rain=(
                    float(rain)
                    if rain not in (None, 0, 0.0)
                    else None
                ),
            )

        except (KeyError, TypeError, ValueError):
            logger.error("Unexpected Open-Meteo response shape")
            raise ExternalServiceError(
                "The weather service returned an unexpected response."
            )

    # --------------------------------------------------------- OpenWeatherMap

    async def _openweathermap(self, lat: float, lon: float) -> Weather:
        if not self._api_key or not self._api_key.get_secret_value():
            raise ConfigurationError(
                "WEATHER_PROVIDER is 'openweathermap' "
                "but WEATHER_API_KEY is not set."
            )

        data = await self._get(
            f"{self._base_url}/data/2.5/weather",
            params={
                "lat": lat,
                "lon": lon,
                "units": "imperial",
                "appid": self._api_key.get_secret_value(),
            },
        )

        try:
            main = data["main"]
            rain_mm = (data.get("rain") or {}).get("1h")

            return Weather(
                temp=float(main["temp"]),
                clouds=_clamp01(float(data["clouds"]["all"]) / 100),
                pressure=float(main["pressure"]),
                humidity=_clamp01(float(main["humidity"]) / 100),
                wind=float(data["wind"]["speed"]),
                rain=(
                    float(rain_mm) / MM_PER_INCH
                    if rain_mm
                    else None
                ),
            )

        except (KeyError, TypeError, ValueError):
            logger.error("Unexpected OpenWeatherMap response shape")
            raise ExternalServiceError(
                "The weather service returned an unexpected response."
            )

    # ---------------------------------------------------------------- HTTP

    async def _get(self, url: str, params: dict) -> dict:
        """
        Make a weather-provider request.

        HTTP 429 is retried with exponential backoff:
            attempt 1 -> wait 2 sec
            attempt 2 -> wait 4 sec
            attempt 3 -> wait 8 sec

        This prevents an immediate burst of repeated requests when the
        provider temporarily rate-limits the application.
        """

        max_attempts = 3

        for attempt in range(max_attempts):
            try:
                response = await self._client.get(
                    url,
                    params=params,
                )

                # -------------------------------------------------
                # Rate limited by weather provider
                # -------------------------------------------------
                if response.status_code == 429:
                    if attempt < max_attempts - 1:
                        retry_after = response.headers.get("Retry-After")

                        if retry_after:
                            try:
                                wait_seconds = min(
                                    float(retry_after),
                                    10.0,
                                )
                            except ValueError:
                                wait_seconds = 2 ** (attempt + 1)
                        else:
                            wait_seconds = 2 ** (attempt + 1)

                        logger.warning(
                            "Weather provider returned HTTP 429. "
                            "Retrying in %.1f seconds "
                            "(attempt %s/%s).",
                            wait_seconds,
                            attempt + 1,
                            max_attempts,
                        )

                        await asyncio.sleep(wait_seconds)
                        continue

                    logger.error(
                        "Weather provider returned HTTP 429 "
                        "after %s attempts.",
                        max_attempts,
                    )

                    raise ExternalServiceError(
                        "The weather service is currently rate limited. "
                        "Please try again shortly."
                    )

                # -------------------------------------------------
                # Other HTTP errors
                # -------------------------------------------------
                response.raise_for_status()

                return response.json()

            except httpx.TimeoutException:
                logger.error("Weather provider timed out")

                raise ExternalTimeoutError(
                    "The weather service timed out. Please try again."
                )

            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code

                logger.error(
                    "Weather provider returned HTTP %s",
                    status,
                )

                if status in (401, 403):
                    raise ConfigurationError(
                        "The weather provider rejected the configured API key."
                    )

                raise ExternalServiceError(
                    "The weather service is currently unavailable."
                )

            except (httpx.HTTPError, ValueError):
                logger.error("Weather request failed")

                raise ExternalServiceError(
                    "The weather service is currently unavailable."
                )