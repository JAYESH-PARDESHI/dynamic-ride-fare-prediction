"""Route distance + duration from a routing provider.

Providers (set ROUTING_PROVIDER in .env):
  osrm             - default, no API key. Uses the public OSRM demo server unless
                     ROUTING_BASE_URL points to your own server. (The public demo
                     server is for light/dev use only.)
  openrouteservice - needs ROUTING_API_KEY.

The model was trained with ``distance`` in MILES, so we convert metres -> miles.
"""
import logging
from dataclasses import dataclass

import httpx

from app.catalog import Location
from app.config import Settings
from app.errors import (
    ConfigurationError,
    ExternalServiceError,
    ExternalTimeoutError,
    RouteNotFoundError,
)
from app.utils.cache import TTLCache

logger = logging.getLogger(__name__)

METERS_PER_MILE = 1609.344
DEFAULT_OSRM_URL = "https://router.project-osrm.org"
DEFAULT_ORS_URL = "https://api.openrouteservice.org"


@dataclass(frozen=True)
class Route:
    distance: float  # miles
    duration: float  # minutes
    source_coordinates: tuple[float, float]  # (latitude, longitude)
    destination_coordinates: tuple[float, float]
    # GeoJSON LineString geometry {"type": "LineString", "coordinates": [[lon, lat], ...]}
    # of the real road route. None unless it was requested (include_geometry=True).
    geometry: dict | None = None


def _valid_geometry(geometry) -> dict:
    """Accept only a GeoJSON LineString with >= 2 [lon, lat] positions."""
    if (
        isinstance(geometry, dict)
        and geometry.get("type") == "LineString"
        and isinstance(geometry.get("coordinates"), list)
        and len(geometry["coordinates"]) >= 2
    ):
        return {
            "type": "LineString",
            "coordinates": [[float(c[0]), float(c[1])] for c in geometry["coordinates"]],
        }
    raise ValueError("bad geometry")


class RoutingService:
    def __init__(self, client: httpx.AsyncClient, settings: Settings):
        self._client = client
        self._provider = settings.routing_provider
        self._api_key = settings.routing_api_key
        self._base_url = (
            settings.routing_base_url
            or (DEFAULT_OSRM_URL if self._provider == "osrm" else DEFAULT_ORS_URL)
        ).rstrip("/")
        # Road routes barely change -> cache for a day. The key is the EXACT coordinates
        # (rounded to ~1 m), so two different points in one neighbourhood never share a route.
        self._cache: TTLCache[Route] = TTLCache(ttl_seconds=24 * 3600, max_entries=5000)

    async def get_route(
        self, source: Location, destination: Location, include_geometry: bool = False
    ) -> Route:
        """Route between the EXACT coordinates of ``source`` and ``destination``.

        ``Location.name`` is only used for logging here - it never affects the route.
        """
        key = (
            round(source.latitude, 5), round(source.longitude, 5),
            round(destination.latitude, 5), round(destination.longitude, 5),
            include_geometry,
        )
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        if self._provider == "osrm":
            meters, seconds, geometry = await self._osrm(source, destination, include_geometry)
        else:
            meters, seconds, geometry = await self._openrouteservice(
                source, destination, include_geometry
            )

        route = Route(
            distance=round(meters / METERS_PER_MILE, 2),
            duration=round(seconds / 60, 1),
            source_coordinates=(source.latitude, source.longitude),
            destination_coordinates=(destination.latitude, destination.longitude),
            geometry=geometry,
        )
        logger.info(
            "Route %s -> %s: %.2f miles, %.1f min, %s points (%s)",
            source.name, destination.name, route.distance, route.duration,
            len(geometry["coordinates"]) if geometry else 0, self._provider,
        )
        self._cache.set(key, route)
        return route

    # ---------------------------------------------------------------- OSRM
    async def _osrm(
        self, a: Location, b: Location, include_geometry: bool
    ) -> tuple[float, float, dict | None]:
        url = (
            f"{self._base_url}/route/v1/driving/"
            f"{a.longitude},{a.latitude};{b.longitude},{b.latitude}"
        )
        params = (
            {"overview": "full", "geometries": "geojson"}
            if include_geometry
            else {"overview": "false"}
        )
        data = await self._request("GET", url, params=params)
        if isinstance(data, dict) and data.get("code") in ("NoRoute", "NoSegment"):
            raise RouteNotFoundError("No driving route could be found between these two points.")
        try:
            if data.get("code") != "Ok":
                raise KeyError("code")
            route = data["routes"][0]
            geometry = _valid_geometry(route["geometry"]) if include_geometry else None
            return float(route["distance"]), float(route["duration"]), geometry
        except (KeyError, IndexError, TypeError, ValueError):
            logger.error("Unexpected OSRM response shape")
            raise ExternalServiceError("The routing service returned an unexpected response.")

    # ------------------------------------------------------ OpenRouteService
    async def _openrouteservice(
        self, a: Location, b: Location, include_geometry: bool
    ) -> tuple[float, float, dict | None]:
        if not self._api_key or not self._api_key.get_secret_value():
            raise ConfigurationError(
                "ROUTING_PROVIDER is 'openrouteservice' but ROUTING_API_KEY is not set."
            )
        # The "/geojson" variant returns the geometry as GeoJSON instead of an encoded polyline.
        url = f"{self._base_url}/v2/directions/driving-car" + ("/geojson" if include_geometry else "")
        data = await self._request(
            "POST",
            url,
            headers={"Authorization": self._api_key.get_secret_value()},
            json={"coordinates": [[a.longitude, a.latitude], [b.longitude, b.latitude]]},
        )
        try:
            if include_geometry:
                feature = data["features"][0]
                summary = feature["properties"]["summary"]
                geometry = _valid_geometry(feature["geometry"])
            else:
                summary = data["routes"][0]["summary"]
                geometry = None
            return float(summary["distance"]), float(summary["duration"]), geometry
        except (KeyError, IndexError, TypeError, ValueError):
            logger.error("Unexpected OpenRouteService response shape")
            raise ExternalServiceError("The routing service returned an unexpected response.")

    # ---------------------------------------------------------------- HTTP
    async def _request(self, method: str, url: str, **kwargs) -> dict:
        try:
            response = await self._client.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException:
            logger.error("Routing provider timed out")
            raise ExternalTimeoutError("The routing service timed out. Please try again.")
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            logger.error("Routing provider returned HTTP %s", status)
            if status in (401, 403):
                raise ConfigurationError("The routing provider rejected the configured API key.")
            raise ExternalServiceError("The routing service is currently unavailable.")
        except (httpx.HTTPError, ValueError):
            logger.error("Routing request failed")
            raise ExternalServiceError("The routing service is currently unavailable.")
