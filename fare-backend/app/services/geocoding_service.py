"""Place search + reverse geocoding (Nominatim / OpenStreetMap by default).

Provider usage policy (https://operations.osmfoundation.org/policies/nominatim/),
and what this module does about it:

  * identifying User-Agent ........ built from GEOCODER_CONTACT (set it in .env)
  * max 1 request / second ........ a scheduler spaces provider calls; callers that
                                    would wait longer than GEOCODER_MAX_QUEUE_SECONDS
                                    get HTTP 429 instead of piling up
  * cache results ................. search + reverse results are cached (24 h default)
  * no heavy autocomplete ......... the frontend must debounce (documented in README)
  * attribution ................... every response carries "(c) OpenStreetMap contributors"

The public server is for light use. For real traffic, self-host Nominatim or switch
provider and set GEOCODER_BASE_URL.
"""
import asyncio
import logging
import re
import time
from dataclasses import dataclass

import httpx

from app.config import Settings
from app.errors import (
    GeocodingRateLimitedError,
    GeocodingTimeoutError,
    GeocodingUnavailableError,
    InvalidRequestError,
    ReverseGeocodeNotFoundError,
)
from app.services.location_mapping_service import AreaMatch, LocationMappingService
from app.utils.cache import TTLCache

logger = logging.getLogger(__name__)

ATTRIBUTION = "(c) OpenStreetMap contributors"
MAX_QUERY_LENGTH = 200
MIN_QUERY_ALNUM = 2
VIEWBOX_MARGIN = 0.01  # degrees (~1 km) around the Boston service area


@dataclass(frozen=True)
class Place:
    display_name: str
    name: str
    latitude: float
    longitude: float
    area: AreaMatch


def clean_query(text: str) -> str:
    query = " ".join(text.split())
    if not query:
        raise InvalidRequestError("Search text must not be empty.")
    if len(query) > MAX_QUERY_LENGTH:
        raise InvalidRequestError(f"Search text is too long (max {MAX_QUERY_LENGTH} characters).")
    if len(re.findall(r"[^\W_]", query)) < MIN_QUERY_ALNUM:
        raise InvalidRequestError("Search text must contain at least 2 letters or digits.")
    return query


class GeocodingService:
    def __init__(self, client: httpx.AsyncClient, settings: Settings, mapper: LocationMappingService):
        self._client = client
        self._mapper = mapper
        self._base_url = settings.geocoder_base_url.rstrip("/")
        contact = settings.geocoder_contact.strip()
        self._headers = {
            "User-Agent": "fare-prediction-backend/1.0" + (f" ({contact})" if contact else "")
        }
        self._min_interval = settings.geocoder_min_interval_seconds
        self._max_queue = settings.geocoder_max_queue_seconds
        self._limit = max(1, settings.geocoder_result_limit)
        self._next_free = 0.0
        ttl = settings.geocoder_cache_seconds
        self._search_cache: TTLCache[list[Place]] = TTLCache(ttl, max_entries=2000)
        self._reverse_cache: TTLCache[Place] = TTLCache(ttl, max_entries=5000)

    # ----------------------------------------------------------------- search
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
                "limit": self._limit * 2,  # some hits are dropped by the service-area filter
                "viewbox": (
                    f"{min_lon - VIEWBOX_MARGIN},{max_lat + VIEWBOX_MARGIN},"
                    f"{max_lon + VIEWBOX_MARGIN},{min_lat - VIEWBOX_MARGIN}"
                ),
                "bounded": 1,
                "countrycodes": "us",
                "dedupe": 1,
            },
        )
        if not isinstance(data, list):
            logger.error("Unexpected geocoder search response shape")
            raise GeocodingUnavailableError("The location search service returned an unexpected response.")

        places: list[Place] = []
        for item in data:
            try:
                lat, lon = float(item["lat"]), float(item["lon"])
                display = str(item["display_name"])
            except (KeyError, TypeError, ValueError):
                continue  # skip malformed items, keep the rest
            area = self._mapper.locate(lat, lon)
            if not area.in_service_area:
                continue  # outside the Boston service area -> not offered
            places.append(Place(display, _short_name(item, display), lat, lon, area))
            if len(places) >= self._limit:
                break

        self._search_cache.set(key, places)  # empty results are cached too (saves provider calls)
        return places

    # ---------------------------------------------------------------- reverse
    async def reverse(self, latitude: float, longitude: float) -> Place:
        """Name for a clicked point. The returned coordinates are the CLICKED ones, unchanged."""
        key = (round(latitude, 5), round(longitude, 5))
        cached = self._reverse_cache.get(key)
        if cached is not None:
            return cached

        data = await self._get(
            "/reverse",
            {"lat": latitude, "lon": longitude, "format": "jsonv2", "zoom": 18},
        )
        if not isinstance(data, dict):
            logger.error("Unexpected geocoder reverse response shape")
            raise GeocodingUnavailableError("The location lookup service returned an unexpected response.")
        if data.get("error") or not data.get("display_name"):
            raise ReverseGeocodeNotFoundError("No address or place was found at that point on the map.")

        display = str(data["display_name"])
        place = Place(
            display, _short_name(data, display), latitude, longitude,
            self._mapper.locate(latitude, longitude),
        )
        self._reverse_cache.set(key, place)
        return place

    # ------------------------------------------------------------------- HTTP
    async def _reserve_slot(self) -> None:
        """Space provider calls >= min_interval apart; refuse if the queue is too long."""
        now = time.monotonic()
        start = max(now, self._next_free)
        wait = start - now
        if wait > self._max_queue:
            raise GeocodingRateLimitedError(
                "Too many location searches right now. Please wait a moment and try again."
            )
        self._next_free = start + self._min_interval  # no await before this -> race-free
        if wait > 0:
            await asyncio.sleep(wait)

    async def _get(self, path: str, params: dict):
        await self._reserve_slot()
        try:
            response = await self._client.get(
                f"{self._base_url}{path}", params=params, headers=self._headers
            )
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException:
            logger.error("Geocoder timed out")
            raise GeocodingTimeoutError("The location service timed out. Please try again.")
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            logger.error("Geocoder returned HTTP %s", status)
            if status == 429:
                raise GeocodingRateLimitedError(
                    "Too many location searches right now. Please wait a moment and try again."
                )
            raise GeocodingUnavailableError("The location service is currently unavailable.")
        except (httpx.HTTPError, ValueError):
            logger.error("Geocoder request failed")
            raise GeocodingUnavailableError("The location service is currently unavailable.")


def _short_name(item: dict, display_name: str) -> str:
    name = item.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return display_name.split(",")[0].strip()
