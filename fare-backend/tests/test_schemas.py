import pytest
from pydantic import ValidationError

from app.schemas import FareRequest

GOOD = {"source": "Beacon Hill", "destination": "Financial District", "cab_type": "Uber", "name": "UberX"}


def test_valid_request():
    assert FareRequest(**GOOD).name == "UberX"


def test_strips_whitespace():
    assert FareRequest(**{**GOOD, "source": "  Beacon Hill  "}).source == "Beacon Hill"


@pytest.mark.parametrize("field", list(GOOD))
def test_missing_field(field):
    data = {k: v for k, v in GOOD.items() if k != field}
    with pytest.raises(ValidationError):
        FareRequest(**data)


@pytest.mark.parametrize("field", list(GOOD))
def test_blank_field(field):
    with pytest.raises(ValidationError):
        FareRequest(**{**GOOD, field: "   "})


@pytest.mark.parametrize("extra", ["distance", "surge_multiplier", "temp", "hour", "date_time"])
def test_rider_cannot_send_backend_computed_fields(extra):
    with pytest.raises(ValidationError):
        FareRequest(**{**GOOD, extra: 1})
