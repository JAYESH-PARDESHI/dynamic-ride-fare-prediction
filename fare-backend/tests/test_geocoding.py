"""Location search + reverse geocoding against a mocked provider (no network)."""
import asyncio

import httpx
import pytest

from app.config import Settings
from app.errors import (
    GeocodingRateLimitedError,
    GeocodingTimeoutError,
    GeocodingUnavailableError,
    InvalidRequestError,
    ReverseGeocodeNotFoundError,
)
from app.services.geocoding_service import GeocodingService
from tests.conftest import run

COPLEY = {"lat": "42.3500", "lon": "-71.0773", "display_name": "Copley Square, Back Bay, Boston, MA, USA", "name": "Copley Square"}
FENWAY_PARK = {"lat": "42.3467", "lon": "-71.0972", "display_name": "Fenway Park, Boston, MA, USA", "name": "Fenway Park"}
CAMBRIDGE = {"lat": "42.3736", "lon": "-71.1190", "display_name": "Harvard Square, Cambridge, MA, USA", "name": "Harvard Square"}
JAMAICA_PLAIN = {"lat": "42.3099", "lon": "-71.1130", "display_name": "Jamaica Pond, Boston, MA, USA", "name": "Jamaica Pond"}


def _settings(**kw):
    kw.setdefault("geocoder_min_interval_seconds", 0.0)
    return Settings(model_path="x", _env_file=None, **kw)


def _run_with(handler, fn, **settings_kw):
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            from app.services.location_mapping_service import LocationMappingService
            svc = GeocodingService(c, _settings(**settings_kw), LocationMappingService.from_data_dir())
            return await fn(svc)
    return run(go())


# ---------------------------------------------------------------- search
def test_search_returns_real_coordinates_and_model_area():
    def handler(request):
        assert request.url.path == "/search"
        return httpx.Response(200, json=[COPLEY])

    (place,) = _run_with(handler, lambda s: s.search("Copley Square"))
    assert place.display_name.startswith("Copley Square")
    assert (place.latitude, place.longitude) == (42.35, -71.0773)
    assert place.area.model_area == "Back Bay"


def test_search_sends_boston_viewbox_and_identifying_user_agent():
    seen = {}

    def handler(request):
        seen["params"] = dict(request.url.params)
        seen["ua"] = request.headers["user-agent"]
        return httpx.Response(200, json=[])

    _run_with(handler, lambda s: s.search("Fenway Park"), geocoder_contact="ops@example.com")
    assert seen["params"]["bounded"] == "1" and seen["params"]["countrycodes"] == "us"
    assert seen["params"]["format"] == "jsonv2" and seen["params"]["q"] == "Fenway Park"
    assert "viewbox" in seen["params"]
    assert "ops@example.com" in seen["ua"] and "fare-prediction-backend" in seen["ua"]


def test_results_outside_boston_are_dropped_and_unmapped_ones_flagged():
    def handler(request):
        return httpx.Response(200, json=[CAMBRIDGE, FENWAY_PARK, JAMAICA_PLAIN])

    places = _run_with(handler, lambda s: s.search("park"))
    assert [p.name for p in places] == ["Fenway Park", "Jamaica Pond"]  # Cambridge dropped
    assert places[0].area.model_area == "Fenway"
    assert places[1].area.in_service_area and places[1].area.model_area is None  # kept, unsupported


def test_malformed_items_are_skipped_not_fatal():
    def handler(request):
        return httpx.Response(200, json=[{"lat": "x"}, {"foo": 1}, COPLEY])

    assert len(_run_with(handler, lambda s: s.search("copley"))) == 1


def test_no_results_is_an_empty_list_not_an_error():
    assert _run_with(lambda r: httpx.Response(200, json=[]), lambda s: s.search("zzzzqqq")) == []


@pytest.mark.parametrize("text", ["", "   ", "a", "!!", "...", "x" * 201])
def test_invalid_queries_are_rejected_without_calling_the_provider(text):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, json=[])

    with pytest.raises(InvalidRequestError):
        _run_with(handler, lambda s: s.search(text))
    assert calls == []


def test_search_results_are_cached_case_and_space_insensitively():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, json=[COPLEY])

    async def fn(s):
        await s.search("Copley Square")
        await s.search("  copley   SQUARE ")
        await s.search("Copley Square")

    _run_with(handler, fn)
    assert len(calls) == 1


def test_empty_results_are_cached_too():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, json=[])

    async def fn(s):
        await s.search("nothing here")
        await s.search("nothing here")

    _run_with(handler, fn)
    assert len(calls) == 1


# ----------------------------------------------------------- provider errors
def test_provider_timeout_maps_to_timeout_error():
    def boom(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(GeocodingTimeoutError):
        _run_with(boom, lambda s: s.search("copley"))


def test_provider_429_maps_to_rate_limited():
    with pytest.raises(GeocodingRateLimitedError):
        _run_with(lambda r: httpx.Response(429), lambda s: s.search("copley"))


@pytest.mark.parametrize("response", [
    httpx.Response(500), httpx.Response(403), httpx.Response(200, text="not json"),
    httpx.Response(200, json={"unexpected": "object"}),
])
def test_other_provider_failures_map_to_unavailable_without_leaking_details(response):
    with pytest.raises(GeocodingUnavailableError) as exc:
        _run_with(lambda r: response, lambda s: s.search("copley"))
    assert "nominatim" not in exc.value.message.lower() and "http" not in exc.value.message.lower()


def test_failed_lookups_are_not_cached():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200 if len(calls) > 1 else 500, json=[COPLEY])

    async def fn(s):
        with pytest.raises(GeocodingUnavailableError):
            await s.search("copley")
        return await s.search("copley")

    assert len(_run_with(handler, fn)) == 1 and len(calls) == 2


# ------------------------------------------------------------ our own limiter
def test_calls_are_spaced_and_an_overlong_queue_is_refused_with_429():
    handler = lambda r: httpx.Response(200, json=[])

    async def fn(s):
        # 1st call: immediate. Following ones are scheduled 1 s apart; with a 1.5 s queue
        # cap, a burst of further distinct queries must be refused instead of waiting 2 s+.
        await s.search("first query")
        with pytest.raises(GeocodingRateLimitedError):
            await asyncio.gather(s.search("second query"), s.search("third query"), s.search("fourth query"))

    _run_with(handler, fn, geocoder_min_interval_seconds=1.0, geocoder_max_queue_seconds=1.5)


# --------------------------------------------------------------- reverse
def test_reverse_keeps_the_clicked_coordinates_and_uses_the_provider_name():
    def handler(request):
        assert request.url.path == "/reverse"
        return httpx.Response(200, json={"display_name": "Copley Square, Boston, MA, USA", "name": "Copley Square",
                                         "lat": "42.35001", "lon": "-71.07731"})  # snapped by provider

    place = _run_with(handler, lambda s: s.reverse(42.3500, -71.0773))
    assert (place.latitude, place.longitude) == (42.3500, -71.0773)  # NOT the provider's snapped point
    assert place.display_name.startswith("Copley Square")
    assert place.area.model_area == "Back Bay"


def test_reverse_nothing_found_is_a_404_style_error_and_no_name_is_invented():
    with pytest.raises(ReverseGeocodeNotFoundError):
        _run_with(lambda r: httpx.Response(200, json={"error": "Unable to geocode"}),
                  lambda s: s.reverse(42.35, -71.07))


def test_reverse_results_are_cached_by_rounded_coordinates():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, json={"display_name": "X, Boston", "name": "X"})

    async def fn(s):
        await s.reverse(42.350001, -71.077301)
        await s.reverse(42.350002, -71.077302)  # same point to ~1 m

    _run_with(handler, fn)
    assert len(calls) == 1


def test_reverse_timeout_and_unavailable():
    def boom(request):
        raise httpx.ConnectTimeout("slow", request=request)

    with pytest.raises(GeocodingTimeoutError):
        _run_with(boom, lambda s: s.reverse(42.35, -71.07))
    with pytest.raises(GeocodingUnavailableError):
        _run_with(lambda r: httpx.Response(503), lambda s: s.reverse(42.35, -71.07))
