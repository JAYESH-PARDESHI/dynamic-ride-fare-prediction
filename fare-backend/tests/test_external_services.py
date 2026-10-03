"""Routing + weather services against httpx.MockTransport (no real network)."""
import httpx
import pytest

from app.catalog import Location
from app.config import Settings
from app.errors import (
    ConfigurationError,
    ExternalServiceError,
    ExternalTimeoutError,
    RouteNotFoundError,
)
from app.services.routing_service import RoutingService
from app.services.weather_service import WeatherService
from tests.conftest import run

A = Location("Beacon Hill", 42.3588, -71.0707)
B = Location("Financial District", 42.3559, -71.0550)


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _settings(**kw):
    return Settings(model_path="x", _env_file=None, **kw)


# --------------------------------------------------------------- routing
def test_osrm_converts_metres_and_seconds():
    def handler(request):
        assert "-71.0707,42.3588;-71.055,42.3559" in str(request.url)  # lon,lat order
        return httpx.Response(200, json={"code": "Ok", "routes": [{"distance": 3862.4, "duration": 540}]})

    async def go():
        async with _client(handler) as c:
            return await RoutingService(c, _settings()).get_route(A, B)

    route = run(go())
    assert route.distance == 2.4          # 3862.4 m = 2.4 miles
    assert route.duration == 9.0          # minutes
    assert route.source_coordinates == (42.3588, -71.0707)


def test_routes_are_cached():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, json={"code": "Ok", "routes": [{"distance": 1000, "duration": 60}]})

    async def go():
        async with _client(handler) as c:
            svc = RoutingService(c, _settings())
            await svc.get_route(A, B)
            await svc.get_route(A, B)

    run(go())
    assert len(calls) == 1


def test_routing_http_error_and_timeout_and_bad_json():
    def make(handler):
        async def go():
            async with _client(handler) as c:
                await RoutingService(c, _settings()).get_route(A, B)
        return go

    with pytest.raises(ExternalServiceError):
        run(make(lambda r: httpx.Response(500))())

    def boom(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ExternalTimeoutError):
        run(make(boom)())

    # "Ok" but no route in the body = malformed provider response -> 502
    with pytest.raises(ExternalServiceError):
        run(make(lambda r: httpx.Response(200, json={"code": "Ok", "routes": []}))())

    # OSRM says there is no driving route between the points -> 422 (a problem with the
    # requested points, not an outage). Changed from 502 when exact coordinates were added.
    with pytest.raises(RouteNotFoundError):
        run(make(lambda r: httpx.Response(200, json={"code": "NoRoute"}))())


def test_openrouteservice_requires_api_key():
    async def go():
        async with _client(lambda r: httpx.Response(200, json={})) as c:
            await RoutingService(c, _settings(routing_provider="openrouteservice")).get_route(A, B)

    with pytest.raises(ConfigurationError):
        run(go())


# --------------------------------------------------------------- weather
def test_openmeteo_converts_percent_to_fraction_and_requests_model_units():
    def handler(request):
        q = request.url.params
        assert q["temperature_unit"] == "fahrenheit"
        assert q["wind_speed_unit"] == "mph"
        assert q["precipitation_unit"] == "inch"
        return httpx.Response(200, json={"current": {
            "temperature_2m": 41.2, "relative_humidity_2m": 80, "cloud_cover": 75,
            "pressure_msl": 1012.3, "wind_speed_10m": 7.5, "rain": 0.0}})

    async def go():
        async with _client(handler) as c:
            return await WeatherService(c, _settings()).get_current_weather(42.35, -71.07)

    w = run(go())
    assert (w.temp, w.clouds, w.humidity, w.pressure, w.wind) == (41.2, 0.75, 0.8, 1012.3, 7.5)
    assert w.rain is None                      # dry -> missing, like the training data
    assert w.to_model_dict()["rain"] != w.to_model_dict()["rain"]  # NaN


def test_openweathermap_converts_mm_to_inches_and_percent():
    def handler(request):
        assert request.url.params["units"] == "imperial"
        return httpx.Response(200, json={
            "main": {"temp": 40.0, "pressure": 1010, "humidity": 90},
            "clouds": {"all": 100}, "wind": {"speed": 12.0}, "rain": {"1h": 2.54}})

    async def go():
        async with _client(handler) as c:
            svc = WeatherService(c, _settings(weather_provider="openweathermap", weather_api_key="secret"))
            return await svc.get_current_weather(42.35, -71.07)

    w = run(go())
    assert w.clouds == 1.0 and w.humidity == 0.9
    assert w.rain == pytest.approx(0.1)        # 2.54 mm = 0.1 in


def test_openweathermap_missing_key_and_rejected_key():
    async def go(key):
        async with _client(lambda r: httpx.Response(401)) as c:
            kw = {"weather_api_key": key} if key else {}
            await WeatherService(c, _settings(weather_provider="openweathermap", **kw)).get_current_weather(1, 2)

    with pytest.raises(ConfigurationError):
        run(go(None))
    with pytest.raises(ConfigurationError) as err:
        run(go("topsecret"))
    assert "topsecret" not in err.value.message


def test_weather_failures_are_clean():
    def boom(request):
        raise httpx.ConnectTimeout("t", request=request)

    async def go(handler):
        async with _client(handler) as c:
            await WeatherService(c, _settings()).get_current_weather(1, 2)

    with pytest.raises(ExternalTimeoutError):
        run(go(boom))
    with pytest.raises(ExternalServiceError):
        run(go(lambda r: httpx.Response(200, json={"unexpected": True})))
