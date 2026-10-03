"""POST /api/v2/fare/predict: service flow + HTTP contract (routing / weather / geocoder mocked)."""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.errors import (
    ExternalServiceError,
    InvalidRequestError,
    InvalidRideOptionError,
    LocationNotMappedError,
    OutsideServiceAreaError,
    SameModelAreaError,
)
from app.main import create_app
from app.schemas import ExactFareRequest
from app.services.demand_service import ALLOWED_SURGE_VALUES
from app.services.geocoding_service import Place
from app.services.location_mapping_service import LocationMappingService
from tests.conftest import MONDAY_EVENING_UTC, FakeRouting, FakeWeather, run

COPLEY = {"latitude": 42.35012, "longitude": -71.07731, "display_name": "Copley Square, Boston, MA"}
FENWAY_PARK = {"latitude": 42.34672, "longitude": -71.09722}
PRUDENTIAL = {"latitude": 42.3472, "longitude": -71.0820}          # also Back Bay
JAMAICA_PLAIN = {"latitude": 42.3099, "longitude": -71.1130}       # in Boston, no model area
CAMBRIDGE = {"latitude": 42.3736, "longitude": -71.1190}           # outside Boston
BODY = {"pickup": COPLEY, "destination": FENWAY_PARK, "cab_type": "Uber", "name": "UberX"}


def req(**over):
    return ExactFareRequest.model_validate({**BODY, **over})


# ------------------------------------------------------------ service flow
def test_exact_prediction_end_to_end(make_service):
    routing, weather = FakeRouting(), FakeWeather()
    resp = run(make_service(routing=routing, weather=weather).predict_exact(req()))

    assert resp.estimated_fare > 0 and resp.currency == "USD"
    assert (resp.pickup.model_area, resp.destination.model_area) == ("Back Bay", "Fenway")
    assert resp.pickup.neighborhood == "Back Bay" and resp.pickup.display_name == "Copley Square, Boston, MA"
    assert resp.destination.display_name is None
    assert resp.route.distance == 2.4 and resp.route.duration == 11.5
    assert resp.route.geometry["type"] == "LineString"
    assert resp.surge_multiplier in ALLOWED_SURGE_VALUES
    assert resp.weather.temperature_f == 41.0 and resp.weather.rain_inches == 0.0


def test_exact_coordinates_not_category_centres_reach_routing_and_weather(make_service):
    routing, weather = FakeRouting(), FakeWeather()
    run(make_service(routing=routing, weather=weather).predict_exact(req()))

    source, destination, include_geometry = routing.last_args
    assert (source.latitude, source.longitude) == (42.35012, -71.07731)
    assert (destination.latitude, destination.longitude) == (42.34672, -71.09722)
    assert include_geometry is True
    assert (source.name, destination.name) == ("Back Bay", "Fenway")  # categories only label them
    assert weather.last_coords == (42.35012, -71.07731)                # pickup, exact


def test_response_echoes_exact_coordinates_unchanged(make_service):
    resp = run(make_service().predict_exact(req()))
    assert (resp.pickup.latitude, resp.pickup.longitude) == (42.35012, -71.07731)
    assert (resp.destination.latitude, resp.destination.longitude) == (42.34672, -71.09722)


def test_rain_is_reported_in_inches(make_service):
    resp = run(make_service(weather=FakeWeather(rain=0.04)).predict_exact(req()))
    assert resp.weather.raining is True and resp.weather.rain_inches == 0.04


# ------------------------------------------------------------ Boston time
def test_timestamp_is_boston_local_time_with_offset(make_service):
    resp = run(make_service().predict_exact(req()))          # 21:30 UTC in October (EDT)
    assert resp.timestamp == "2026-10-05T17:30:00-04:00" and resp.timezone == "America/New_York"


def test_timestamp_follows_boston_daylight_saving(make_service):
    winter = datetime(2026, 1, 12, 15, 0, tzinfo=timezone.utc)   # EST = UTC-5
    resp = run(make_service(clock=lambda: winter).predict_exact(req()))
    assert resp.timestamp == "2026-01-12T10:00:00-05:00"


def test_surge_uses_boston_not_utc_hour(make_service):
    # 21:30 UTC = 17:30 Boston (evening rush) -> surge; 16:00 UTC = 12:00 Boston -> none
    rush = run(make_service().predict_exact(req(pickup=COPLEY, destination={"latitude": 42.3556, "longitude": -71.0553})))
    midday = run(make_service(clock=lambda: datetime(2026, 10, 5, 16, 0, tzinfo=timezone.utc)).predict_exact(req()))
    assert rush.surge_multiplier > 1.0 and midday.surge_multiplier == 1.0


class SpyPipeline:
    """Wraps the real pipeline and remembers the frame it was given."""
    def __init__(self, inner):
        self.inner, self.frame = inner, None

    def predict(self, frame):
        self.frame = frame
        return self.inner.predict(frame)


def test_model_receives_utc_by_default_matching_its_training_data(make_service, pipeline):
    spy = SpyPipeline(pipeline)
    run(make_service(pipe=spy).predict_exact(req()))
    assert spy.frame["date_time"].iloc[0] == datetime(2026, 10, 5, 21, 30)      # UTC wall clock
    assert spy.frame["source"].iloc[0] == "Back Bay" and spy.frame["destination"].iloc[0] == "Fenway"
    assert list(spy.frame.columns) == [
        "distance", "cab_type", "destination", "source", "surge_multiplier", "name",
        "date_time", "hour_date", "temp", "clouds", "pressure", "rain", "humidity", "wind"]


def test_model_clock_boston_switch_sends_boston_wall_clock(make_service, pipeline, settings):
    spy = SpyPipeline(pipeline)
    cfg = settings.model_copy(update={"model_clock": "boston"})
    run(make_service(pipe=spy, cfg=cfg).predict_exact(req()))
    assert spy.frame["date_time"].iloc[0] == datetime(2026, 10, 5, 17, 30)
    assert spy.frame["hour_date"].iloc[0] == datetime(2026, 10, 5, 17, 0)


# ------------------------------------------------------------ validation
def test_outside_service_area_rejected_before_any_external_call(make_service):
    routing = FakeRouting()
    with pytest.raises(OutsideServiceAreaError):
        run(make_service(routing=routing).predict_exact(req(destination=CAMBRIDGE)))
    assert routing.calls == 0


def test_unmapped_boston_location_rejected_never_priced_as_nearest(make_service):
    routing = FakeRouting()
    with pytest.raises(LocationNotMappedError) as exc:
        run(make_service(routing=routing).predict_exact(req(pickup=JAMAICA_PLAIN)))
    assert "Jamaica Plain" in exc.value.message and routing.calls == 0


def test_same_model_area_rejected(make_service):
    with pytest.raises(SameModelAreaError) as exc:
        run(make_service().predict_exact(req(destination=PRUDENTIAL)))
    assert "Back Bay" in exc.value.message


def test_same_point_rejected(make_service):
    with pytest.raises(InvalidRequestError):
        run(make_service().predict_exact(req(destination=COPLEY)))


def test_unsupported_ride_option_rejected(make_service):
    with pytest.raises(InvalidRideOptionError):
        run(make_service().predict_exact(req(name="Lux")))
    with pytest.raises(InvalidRideOptionError):
        run(make_service().predict_exact(req(cab_type="Taxi")))


def test_routing_failure_propagates(make_service):
    with pytest.raises(ExternalServiceError):
        run(make_service(routing=FakeRouting(fail_with=ExternalServiceError("down"))).predict_exact(req()))


# ---------------------------------------------------------------- HTTP
class FakeGeocoder:
    def __init__(self, mapper):
        self.mapper = mapper

    async def search(self, text):
        return [Place("Copley Square, Boston, MA", "Copley Square", 42.35, -71.0773, self.mapper.locate(42.35, -71.0773)),
                Place("Jamaica Pond, Boston, MA", "Jamaica Pond", 42.3099, -71.1130, self.mapper.locate(42.3099, -71.1130))]

    async def reverse(self, lat, lon):
        return Place("Copley Square, Boston, MA", "Copley Square", lat, lon, self.mapper.locate(lat, lon))


@pytest.fixture
def client(settings, make_service, mapper):
    app = create_app(settings)
    with TestClient(app, raise_server_exceptions=False) as c:
        c.app.dependency_overrides[app.state.get_fare_service] = lambda: make_service()
        c.app.dependency_overrides[app.state.get_geocoder] = lambda: FakeGeocoder(mapper)
        yield c


def test_http_predict_v2_success_and_contract_shape(client):
    r = client.post("/api/v2/fare/predict", json=BODY)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"estimated_fare", "currency", "cab_type", "name", "pickup", "destination",
                         "route", "surge_multiplier", "demand_score", "weather", "timestamp",
                         "timezone", "disclaimer"}
    assert set(body["pickup"]) == {"latitude", "longitude", "display_name", "neighborhood", "model_area"}
    assert set(body["route"]) == {"distance", "distance_unit", "duration", "duration_unit", "geometry"}
    assert set(body["weather"]) == {"temperature_f", "cloud_cover_pct", "humidity_pct", "wind_mph",
                                    "pressure_mb", "raining", "rain_inches"}
    assert body["route"]["geometry"]["coordinates"][0] == [-71.07731, 42.35012]
    assert body["timestamp"].endswith("-04:00")


@pytest.mark.parametrize("pickup", [
    {"latitude": 91, "longitude": -71.0},
    {"latitude": -91, "longitude": -71.0},
    {"latitude": 42.35, "longitude": 181},
    {"latitude": 42.35, "longitude": -181},
    {"latitude": "abc", "longitude": -71.0},
    {"latitude": 42.35},
    {"latitude": 42.35, "longitude": -71.0, "altitude": 3},
])
def test_http_invalid_coordinates_are_422_invalid_request(client, pickup):
    r = client.post("/api/v2/fare/predict", json={**BODY, "pickup": pickup})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"


def test_http_nan_coordinate_rejected(client):
    r = client.post("/api/v2/fare/predict", content='{"pickup":{"latitude":NaN,"longitude":-71},'
                    '"destination":{"latitude":42.34,"longitude":-71.09},"cab_type":"Uber","name":"UberX"}',
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 422


@pytest.mark.parametrize("override,status,code", [
    ({"destination": CAMBRIDGE}, 422, "outside_service_area"),
    ({"pickup": JAMAICA_PLAIN}, 422, "location_not_mapped"),
    ({"destination": PRUDENTIAL}, 422, "same_model_area"),
    ({"destination": COPLEY}, 422, "invalid_request"),
    ({"name": "Lux"}, 422, "invalid_ride_option"),
    ({"cab_type": "Taxi"}, 422, "invalid_ride_option"),
    ({"source": "Back Bay"}, 422, "invalid_request"),   # old fields are not accepted by v2
])
def test_http_error_codes(client, override, status, code):
    r = client.post("/api/v2/fare/predict", json={**BODY, **override})
    assert r.status_code == status and r.json()["error"]["code"] == code
    assert set(r.json()) == {"error"} and set(r.json()["error"]) == {"code", "message"}


def test_http_v1_predict_still_works_and_is_flagged_deprecated(client):
    legacy = {"source": "Beacon Hill", "destination": "Financial District", "cab_type": "Uber", "name": "UberX"}
    r = client.post("/api/v1/fare/predict", json=legacy)
    assert r.status_code == 200 and "estimated_fare" in r.json() and r.json()["source"] == "Beacon Hill"
    assert r.headers["deprecation"] == "true" and "/api/v2/fare/predict" in r.headers["link"]


def test_http_v1_locations_unchanged(client):
    r = client.get("/api/v1/locations")
    assert r.status_code == 200 and "Beacon Hill" in r.json()["sources"]


def test_http_location_search(client):
    r = client.get("/api/v1/locations/search", params={"q": "  Copley   Square "})
    assert r.status_code == 200
    body = r.json()
    assert body["query"] == "Copley Square" and body["attribution"]
    first, second = body["results"]
    assert first == {"display_name": "Copley Square, Boston, MA", "name": "Copley Square", "latitude": 42.35,
                     "longitude": -71.0773, "neighborhood": "Back Bay", "model_area": "Back Bay", "supported": True}
    assert second["supported"] is False and second["model_area"] is None


def test_http_location_search_missing_query_is_422(client):
    r = client.get("/api/v1/locations/search")
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"


def test_http_reverse_geocode(client):
    r = client.get("/api/v1/locations/reverse", params={"latitude": 42.35, "longitude": -71.0773})
    assert r.status_code == 200
    body = r.json()
    assert body["display_name"] == "Copley Square, Boston, MA"
    assert (body["latitude"], body["longitude"]) == (42.35, -71.0773)
    assert body["model_area"] == "Back Bay" and body["supported"] is True and body["message"] is None


def test_http_reverse_unsupported_boston_point_explains_why(client):
    r = client.get("/api/v1/locations/reverse", params={"latitude": 42.3099, "longitude": -71.1130})
    body = r.json()
    assert r.status_code == 200 and body["supported"] is False and body["model_area"] is None
    assert "Jamaica Plain" in body["message"]


@pytest.mark.parametrize("params,status,code", [
    ({"latitude": 42.3736, "longitude": -71.1190}, 422, "outside_service_area"),
    ({"latitude": 95, "longitude": -71}, 422, "invalid_request"),
    ({"latitude": 42.3}, 422, "invalid_request"),
])
def test_http_reverse_errors(client, params, status, code):
    r = client.get("/api/v1/locations/reverse", params=params)
    assert r.status_code == status and r.json()["error"]["code"] == code


def test_search_and_reverse_work_even_when_model_failed_to_load(tmp_path):
    cfg = Settings(model_path=str(tmp_path / "missing.pkl"), _env_file=None)
    with TestClient(create_app(cfg)) as c:
        assert c.app.state.geocoder is not None and c.app.state.mapper is not None
        r = c.get("/api/v1/locations/reverse", params={"latitude": 42.3736, "longitude": -71.1190})
        assert r.status_code == 422 and r.json()["error"]["code"] == "outside_service_area"  # local check, no network
