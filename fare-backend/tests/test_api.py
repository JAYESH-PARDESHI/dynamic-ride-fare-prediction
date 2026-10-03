"""HTTP-level tests with FastAPI's TestClient (routing/weather mocked)."""
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.errors import ExternalServiceError, ExternalTimeoutError
from app.main import create_app
from tests.conftest import FakeRouting, FakeWeather

GOOD = {"source": "Beacon Hill", "destination": "Financial District", "cab_type": "Uber", "name": "UberX"}


@pytest.fixture
def client(settings, make_service):
    app = create_app(settings)
    with TestClient(app, raise_server_exceptions=False) as c:
        c.app.dependency_overrides[app.state.get_fare_service] = lambda: make_service()
        yield c


def test_health_ok_when_model_loaded(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "model_loaded": True, "detail": None}


def test_health_degraded_with_helpful_message_when_model_missing(tmp_path):
    cfg = Settings(model_path=str(tmp_path / "nope.pkl"), _env_file=None)
    with TestClient(create_app(cfg)) as c:
        r = c.get("/health")
        assert r.status_code == 503
        assert r.json()["status"] == "degraded"
        assert "Model file not found" in r.json()["detail"]
        # prediction endpoint fails cleanly too
        p = c.post("/api/v1/fare/predict", json=GOOD)
        assert p.status_code == 503 and p.json()["error"]["code"] == "model_unavailable"


def test_predict_success(client):
    r = client.post("/api/v1/fare/predict", json=GOOD)
    assert r.status_code == 200, r.text
    body = r.json()
    for key in ("estimated_fare", "currency", "source", "destination", "distance",
                "duration", "surge_multiplier", "demand_score", "weather", "timestamp"):
        assert key in body
    assert body["currency"] == "USD" and body["distance"] == 2.4


def test_predict_unsupported_location_is_422_with_clear_message(client):
    r = client.post("/api/v1/fare/predict", json={**GOOD, "source": "Cambridge"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "unsupported_location"
    assert "currently trained model" in r.json()["error"]["message"]


def test_predict_invalid_ride_name_is_422(client):
    r = client.post("/api/v1/fare/predict", json={**GOOD, "name": "Lux"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_ride_option"


@pytest.mark.parametrize("payload", [
    {}, {"source": "Beacon Hill"}, {**GOOD, "distance": 3.0}, {**GOOD, "source": ""},
])
def test_malformed_requests_are_422(client, payload):
    r = client.post("/api/v1/fare/predict", json=payload)
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"


def test_non_json_body_is_422(client):
    r = client.post("/api/v1/fare/predict", content="not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 422


def test_upstream_errors_map_to_502_and_504(settings, make_service):
    app = create_app(settings)
    with TestClient(app) as c:
        key = app.state.get_fare_service
        app.dependency_overrides[key] = lambda: make_service(
            routing=FakeRouting(fail_with=ExternalServiceError("The routing service is currently unavailable.")))
        assert c.post("/api/v1/fare/predict", json=GOOD).status_code == 502

        app.dependency_overrides[key] = lambda: make_service(
            weather=FakeWeather(fail_with=ExternalTimeoutError("The weather service timed out.")))
        r = c.post("/api/v1/fare/predict", json=GOOD)
        assert r.status_code == 504 and r.json()["error"]["code"] == "external_service_timeout"


def test_locations_endpoint(client):
    r = client.get("/api/v1/locations")
    assert r.status_code == 200 and "Beacon Hill" in r.json()["sources"]


def test_cors_allows_configured_origin(settings):
    cfg = settings.model_copy(update={"cors_allowed_origins": "http://localhost:5173"})
    with TestClient(create_app(cfg)) as c:
        ok = c.get("/health", headers={"Origin": "http://localhost:5173"})
        bad = c.get("/health", headers={"Origin": "http://evil.example"})
        assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
        assert "access-control-allow-origin" not in bad.headers
