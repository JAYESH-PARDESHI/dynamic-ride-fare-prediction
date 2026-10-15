```python
"""Place search + reverse geocoding using Nominatim by default.

Important:
- Identifying User-Agent using GEOCODER_CONTACT.
- Spaces provider requests using an async scheduler.
- Caches search and reverse-geocoding results.
- Honors Retry-After when Nominatim returns HTTP 429.
- Temporarily pauses requests after a rate-limit response.
- Preserves OpenStreetMap attribution.

The scheduler is process-local. Multiple workers or instances require a
shared rate limiter to enforce a global provider request limit.
"""

import asyncio
import logging
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

from app.config import Settings
from app.errors import (
    GeocodingRateLimitedError,
    GeocodingTimeoutError,
    GeocodingUnavailableError,
    InvalidRequestError,
    ReverseGeocodeNotFoundError,
)
from app.services.location_mapping_service import (
    AreaMatch,
    LocationMappingService,
)
from app.utils.cache import TTLCache

logger = logging.getLogger(__name__)

ATTRIBUTION = "(c) OpenStreetMap contributors"
MAX_QUERY_LENGTH = 200
MIN_QUERY_ALNUM = 2
VIEWBOX_MARGIN = 0.01


class Place:
    def __init__(
        self,
        display_name: str,
        name: str,
        latitude: float,
        longitude: float,
        area: AreaMatch,
    ):
        self.display_name = display_name
        self.name = name
        self.latitude = latitude
        self.longitude = longitude
        self.area = area


def clean_query(text: str) -> str:
    query = " ".join(text.split())

    if not query:
        raise InvalidRequestError("Search text must not be empty.")

    if len(query) > MAX_QUERY_LENGTH:
        raise InvalidRequestError(
            f"Search text is too long (max {MAX_QUERY_LENGTH} characters)."
        )

    if len(re.findall(r"[^\W_]", query)) < MIN_QUERY_ALNUM:
        raise InvalidRequestError(
            "Search text must contain at least 2 letters or digits."
        )

    return query


class GeocodingService:
    def __init__(
        self,
        client: httpx.AsyncClient,
        settings: Settings,
        mapper: LocationMappingService,
    ):
        self._client = client
        self._mapper = mapper
        self._base_url = settings.geocoder_base_url.rstrip("/")

        contact = settings.geocoder_contact.strip()
        self._headers = {
            "User-Agent": "fare-prediction-backend/1.0"
            + (f" ({contact})" if contact else "")
        }

        self._min_interval = max(
            1.0, settings.geocoder_min_interval_seconds
        )
        self._max_queue = max(0.0, settings.geocoder_max_queue_seconds)
        self._limit = max(1, settings.geocoder_result_limit)

        # Protects scheduling and provider cooldown state.
        self._scheduler_lock = asyncio.Lock()
        self._next_free = 0.0
        self._blocked_until = 0.0

        ttl = settings.geocoder_cache_seconds
        self._search_cache: TTLCache[list[Place]] = TTLCache(
            ttl, max_entries=2000
        )
        self._reverse_cache: TTLCache[Place] = TTLCache(
            ttl, max_entries=5000
        )

    # --------------------------------------------------------------- search
    async def search(self, text: str) -> list[Place]:
        query = clean_query(text)
        key = query.casefold()

        cached = self._search_cache.get(key)
        if cached is not None:
            return cached

        min_lon, min_lat, max_lon, max_lat = self._mapper.bbox

        data = await self._get(
            "/search",
            {
                "q": query,
                "format": "jsonv2",
                "limit": self._limit * 2,
                "viewbox": (
                    f"{min_lon - VIEWBOX_MARGIN},"
                    f"{max_lat + VIEWBOX_MARGIN},"
                    f"{max_lon + VIEWBOX_MARGIN},"
                    f"{min_lat - VIEWBOX_MARGIN}"
                ),
                "bounded": 1,
                "countrycodes": "us",
                "dedupe": 1,
            },
        )

        if not isinstance(data, list):
            logger.error("Unexpected geocoder search response shape")
            raise GeocodingUnavailableError(
                "The location search service returned an unexpected response."
            )

        places: list[Place] = []

        for item in data:
            if not isinstance(item, dict):
                continue

            try:
                lat = float(item["lat"])
                lon = float(item["lon"])
                display = str(item["display_name"])
            except (KeyError, TypeError, ValueError):
                continue

            area = self._mapper.locate(lat, lon)

            if not area.in_service_area:
                continue

            places.append(
                Place(
                    display_name=display,
                    name=_short_name(item, display),
                    latitude=lat,
                    longitude=lon,
                    area=area,
                )
            )

            if len(places) >= self._limit:
                break

        # Cache empty results too, reducing repeated provider calls.
        self._search_cache.set(key, places)
        return places

    # --------------------------------------------------------------- reverse
    async def reverse(
        self,
        latitude: float,
        longitude: float,
    ) -> Place:
        """Resolve a clicked point; preserve its original coordinates."""
        key = (round(latitude, 5), round(longitude, 5))

        cached = self._reverse_cache.get(key)
        if cached is not None:
            return cached

        data = await self._get(
            "/reverse",
            {
                "lat": latitude,
                "lon": longitude,
                "format": "jsonv2",
                "zoom": 18,
            },
        )

        if not isinstance(data, dict):
            logger.error("Unexpected geocoder reverse response shape")
            raise GeocodingUnavailableError(
                "The location lookup service returned an unexpected response."
            )

        if data.get("error") or not data.get("display_name"):
            raise ReverseGeocodeNotFoundError(
                "No address or place was found at that point on the map."
            )

        display = str(data["display_name"])

        place = Place(
            display_name=display,
            name=_short_name(data, display),
            latitude=latitude,
            longitude=longitude,
            area=self._mapper.locate(latitude, longitude),
        )

        self._reverse_cache.set(key, place)
        return place

    # ----------------------------------------------------------- rate limiter
    async def _reserve_slot(self) -> None:
        """Reserve a spaced request slot, respecting any provider cooldown."""
        while True:
            async with self._scheduler_lock:
                now = time.monotonic()

                start = max(
                    now,
                    self._next_free,
                    self._blocked_until,
                )
                wait = start - now

                if wait > self._max_queue:
                    raise GeocodingRateLimitedError(
                        "Location search is temporarily busy or rate-limited. "
                        "Please wait a moment and try again."
                    )

                self._next_free = start + self._min_interval

            if wait > 0:
                await asyncio.sleep(wait)

            # A different request may have received HTTP 429 while we slept.
            # Re-check the cooldown before allowing this request through.
            async with self._scheduler_lock:
                if time.monotonic() < self._blocked_until:
                    continue

                return

    @staticmethod
    def _retry_after_seconds(response: httpx.Response) -> float:
        """Parse Retry-After as seconds or an HTTP date."""
        value = response.headers.get("Retry-After")

        if not value:
            return 5.0

        try:
            return max(0.0, float(value))
        except ValueError:
            pass

        try:
            retry_at = parsedate_to_datetime(value)

            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)

            now = datetime.now(timezone.utc)
            return max(0.0, (retry_at - now).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return 5.0

    async def _apply_rate_limit(self, response: httpx.Response) -> None:
        """Pause future requests after a provider rate-limit response."""
        delay = self._retry_after_seconds(response)
        blocked_until = time.monotonic() + delay

        async with self._scheduler_lock:
            self._blocked_until = max(
                self._blocked_until,
                blocked_until,
            )
            self._next_free = max(
                self._next_free,
                self._blocked_until,
            )

        logger.warning(
            "Geocoder rate-limited requests; pausing for %.1f seconds",
            delay,
        )

    # ------------------------------------------------------------------- HTTP
    async def _get(self, path: str, params: dict):
        await self._reserve_slot()

        try:
            response = await self._client.get(
                f"{self._base_url}{path}",
                params=params,
                headers=self._headers,
            )

            if response.status_code == 429:
                await self._apply_rate_limit(response)
                raise GeocodingRateLimitedError(
                    "The location service is rate-limiting requests. "
                    "Please wait a moment and try again."
                )

            response.raise_for_status()
            return response.json()

        except GeocodingRateLimitedError:
            raise

        except httpx.TimeoutException as exc:
            logger.warning("Geocoder request timed out")
            raise GeocodingTimeoutError(
                "The location service timed out. Please try again."
            ) from exc

        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Geocoder returned HTTP %s",
                exc.response.status_code,
            )
            raise GeocodingUnavailableError(
                "The location service is currently unavailable."
            ) from exc

        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Geocoder request failed: %s", type(exc).__name__)
            raise GeocodingUnavailableError(
                "The location service is currently unavailable."
            ) from exc


def _short_name(item: dict, display_name: str) -> str:
    name = item.get("name")

    if isinstance(name, str) and name.strip():
        return name.strip()

    return display_name.split(",")[0].strip()
```
