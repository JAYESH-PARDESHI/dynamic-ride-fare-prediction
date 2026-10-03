"""Exact-coordinate OSRM / OpenRouteService routing (+ geometry) and weather lookup. Mocked HTTP."""
import httpx
import pytest

from app.catalog import Location
from app.config import Settings
from app.errors import ExternalServiceError, RouteNotFoundError
from app.services.routing_service import RoutingService
from app.services.weather_service import WeatherService
from tests.conftest import run

COPLEY = Location("Back Bay", 42.35012, -71.07731)
FENWAY_PARK = Location("Fenway", 42.34672, -71.09722)
LINE = {"type": "LineString", "coordinates": [[-71.07731, 42.35012], [-71.0850, 42.3490], [-71.09722, 42.34672]]}


def _settings(**kw):
    return Settings(model_path="x", _env_file=None, **kw)


def _call(handler, fn, **kw):
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            return await fn(RoutingService(c, _settings(**kw)))
    return run(go())


def test_osrm_gets_the_exact_coordinates_not_neighbourhood_centres():
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        return httpx.Response(200, json={"code": "Ok", "routes": [{"distance": 1609.344, "duration": 300, "geometry": LINE}]})

    _call(handler, lambda s: s.get_route(COPLEY, FENWAY_PARK, include_geometry=True))
    assert seen["path"].endswith("/-71.07731,42.35012;-71.09722,42.34672")  # lon,lat;lon,lat


def test_osrm_geometry_is_requested_as_geojson_and_returned_as_a_linestring():
    seen = {}

    def handler(request):
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"code": "Ok", "routes": [{"distance": 3218.688, "duration": 600, "geometry": LINE}]})

    route = _call(handler, lambda s: s.get_route(COPLEY, FENWAY_PARK, include_geometry=True))
    assert seen["params"] == {"overview": "full", "geometries": "geojson"}
    assert route.distance == 2.0 and route.duration == 10.0  # metres -> miles, seconds -> minutes
    assert route.geometry["type"] == "LineString" and len(route.geometry["coordinates"]) == 3
    assert route.geometry["coordinates"][0] == [-71.07731, 42.35012]  # [lon, lat]


def test_geometry_is_not_requested_unless_asked_for():
    seen = {}

    def handler(request):
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"code": "Ok", "routes": [{"distance": 1000, "duration": 60}]})

    route = _call(handler, lambda s: s.get_route(COPLEY, FENWAY_PARK))
    assert seen["params"] == {"overview": "false"} and route.geometry is None


def test_different_points_in_the_same_neighbourhood_get_different_routes_and_cache_entries():
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={"code": "Ok", "routes": [{"distance": 1000, "duration": 60}]})

    other = Location("Back Bay", 42.3472, -71.0820)  # Prudential Center, also "Back Bay"

    async def fn(s):
        await s.get_route(COPLEY, FENWAY_PARK)
        await s.get_route(COPLEY, FENWAY_PARK)   # cached
        await s.get_route(other, FENWAY_PARK)    # same model area, different exact point

    _call(handler, fn)
    assert len(calls) == 2 and calls[0] != calls[1]


def test_malformed_geometry_is_a_clean_502():
    bad = {"code": "Ok", "routes": [{"distance": 1, "duration": 1, "geometry": {"type": "Point", "coordinates": [0, 0]}}]}
    with pytest.raises(ExternalServiceError):
        _call(lambda r: httpx.Response(200, json=bad), lambda s: s.get_route(COPLEY, FENWAY_PARK, include_geometry=True))


def test_no_route_is_422_not_a_provider_outage():
    with pytest.raises(RouteNotFoundError):
        _call(lambda r: httpx.Response(200, json={"code": "NoRoute"}), lambda s: s.get_route(COPLEY, FENWAY_PARK, True))


def test_openrouteservice_geometry_uses_the_geojson_endpoint():
    seen = {}

    def handler(request):
        seen["path"], seen["body"] = request.url.path, request.content
        return httpx.Response(200, json={"features": [{
            "geometry": LINE, "properties": {"summary": {"distance": 1609.344, "duration": 120}}}]})

    route = _call(handler, lambda s: s.get_route(COPLEY, FENWAY_PARK, include_geometry=True),
                  routing_provider="openrouteservice", routing_api_key="k")
    assert seen["path"].endswith("/driving-car/geojson")
    assert route.distance == 1.0 and route.geometry["type"] == "LineString"


# ---------------------------------------------------------------- weather
def test_weather_uses_the_exact_coordinates_and_returns_all_fields():
    seen = {}

    def handler(request):
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"current": {
            "temperature_2m": 55.4, "relative_humidity_2m": 62, "cloud_cover": 40,
            "pressure_msl": 1014.2, "wind_speed_10m": 8.1, "rain": 0.02}})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            return await WeatherService(c, _settings()).get_current_weather(42.35012, -71.07731)

    w = run(go())
    assert seen["params"]["latitude"] == "42.35012" and seen["params"]["longitude"] == "-71.07731"
    assert (w.temp, w.humidity, w.clouds, w.pressure, w.wind, w.rain) == (55.4, 0.62, 0.4, 1014.2, 8.1, 0.02)
