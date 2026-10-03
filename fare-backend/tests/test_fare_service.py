import math
from datetime import datetime, timezone

import pytest

from app.config import Settings
from app.errors import (
    ExternalServiceError,
    ExternalTimeoutError,
    InvalidRequestError,
    InvalidRideOptionError,
    UnsupportedLocationError,
)
from app.schemas import FareRequest
from app.services.demand_service import ALLOWED_SURGE_VALUES
from app.services.fare_service import MODEL_INPUT_COLUMNS, build_model_input
from tests.conftest import MONDAY_EVENING_UTC, FakeRouting, FakeWeather, run

REQ = FareRequest(source="Beacon Hill", destination="Financial District", cab_type="Uber", name="UberX")


def _frame(catalog, weather=None, now=MONDAY_EVENING_UTC):
    src = catalog.resolve_location("Beacon Hill", "source")
    dst = catalog.resolve_location("Financial District", "destination")
    route = run(FakeRouting().get_route(src, dst))
    weather = weather or run(FakeWeather().get_current_weather(0, 0))
    return build_model_input(
        route=route, weather=weather, source=src, destination=dst, cab_type="Uber",
        ride_name="UberX", surge_multiplier=1.75, now_utc=now,
    )


# ------------------------------------------------------------ model input
def test_model_input_has_exactly_the_14_raw_training_columns(catalog):
    frame = _frame(catalog)
    assert list(frame.columns) == MODEL_INPUT_COLUMNS
    assert len(frame) == 1


def test_model_input_is_raw_not_encoded(catalog):
    row = _frame(catalog).iloc[0]
    assert row["source"] == "Beacon Hill" and row["destination"] == "Financial District"
    assert row["cab_type"] == "Uber" and row["name"] == "UberX"
    assert not any(c.startswith(("source_", "destination_", "hour_sin")) for c in _frame(catalog).columns)
    assert "demand" not in " ".join(_frame(catalog).columns)  # demand never reaches the model


def test_model_clock_is_naive_utc_like_training(catalog):
    frame = _frame(catalog)
    assert str(frame["date_time"].dtype).startswith("datetime64")
    assert frame["date_time"].iloc[0] == datetime(2026, 10, 5, 21, 30)  # UTC, not Boston 17:30
    assert frame["hour_date"].iloc[0] == datetime(2026, 10, 5, 21, 0)


def test_dry_weather_gives_nan_rain_and_rainy_gives_value(catalog):
    from app.services.weather_service import Weather
    dry = _frame(catalog, Weather(40, 0.5, 1010, 0.7, 5, None))
    wet = _frame(catalog, Weather(40, 0.5, 1010, 0.7, 5, 0.03))
    assert math.isnan(dry["rain"].iloc[0])
    assert wet["rain"].iloc[0] == 0.03
    assert str(dry["rain"].dtype) == "float64"


# ------------------------------------------------------- real pipeline run
def test_pipeline_accepts_the_frame_and_returns_a_number(pipeline, catalog):
    pred = pipeline.predict(_frame(catalog))
    assert pred.shape == (1,) and math.isfinite(float(pred[0]))


def test_pipeline_handles_rain_and_dry_frames(pipeline, catalog):
    from app.services.weather_service import Weather
    for rain in (None, 0.05):
        assert math.isfinite(float(pipeline.predict(_frame(catalog, Weather(40, 0.5, 1010, 0.7, 5, rain)))[0]))


# ------------------------------------------------------------- full service
def test_full_prediction_flow(make_service):
    resp = run(make_service().predict_fare(REQ))
    assert resp.estimated_fare > 0 and resp.currency == "USD"
    assert resp.source == "Beacon Hill" and resp.destination == "Financial District"
    assert resp.distance == 2.4 and resp.duration == 11.5
    assert resp.surge_multiplier in ALLOWED_SURGE_VALUES
    assert resp.timestamp.startswith("2026-10-05T21:30:00")
    assert resp.weather.temperature_f == 41.0 and resp.weather.raining is False


def test_monday_5_30pm_boston_time_drives_surge(make_service):
    # 17:30 Boston on a weekday with a commuter-hub destination -> surge > 1
    resp = run(make_service().predict_fare(REQ))
    assert resp.surge_multiplier > 1.0


def test_off_peak_boston_time_gives_no_surge(make_service):
    midday_utc = datetime(2026, 10, 5, 16, 0, tzinfo=timezone.utc)  # 12:00 Boston
    resp = run(make_service(clock=lambda: midday_utc).predict_fare(REQ))
    assert resp.surge_multiplier == 1.0


def test_surge_can_be_limited_to_some_cab_types(make_service):
    cfg = Settings(surge_cab_types="Lyft", model_path="x", _env_file=None)
    uber = run(make_service(cfg=cfg).predict_fare(REQ))
    lyft = run(make_service(cfg=cfg).predict_fare(REQ.model_copy(update={"cab_type": "Lyft", "name": "Lyft"})))
    assert uber.surge_multiplier == 1.0
    assert lyft.surge_multiplier > 1.0


def test_unsupported_location_rejected_before_any_external_call(make_service):
    routing = FakeRouting()
    with pytest.raises(UnsupportedLocationError):
        run(make_service(routing=routing).predict_fare(REQ.model_copy(update={"source": "Cambridge"})))
    assert routing.calls == 0


def test_same_source_and_destination_rejected(make_service):
    with pytest.raises(InvalidRequestError):
        run(make_service().predict_fare(REQ.model_copy(update={"destination": "beacon hill"})))


def test_invalid_ride_option_rejected(make_service):
    with pytest.raises(InvalidRideOptionError):
        run(make_service().predict_fare(REQ.model_copy(update={"name": "Lux"})))


def test_routing_failure_is_propagated_cleanly(make_service):
    svc = make_service(routing=FakeRouting(fail_with=ExternalServiceError("routing down")))
    with pytest.raises(ExternalServiceError):
        run(svc.predict_fare(REQ))


def test_weather_timeout_is_propagated_cleanly(make_service):
    svc = make_service(weather=FakeWeather(fail_with=ExternalTimeoutError("slow")))
    with pytest.raises(ExternalTimeoutError):
        run(svc.predict_fare(REQ))
