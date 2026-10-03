import itertools
from datetime import datetime

import pytest

from app.services.demand_service import (
    ALLOWED_SURGE_VALUES,
    LOCATION_WEIGHTS,
    calculate_demand_score,
    calculate_surge_multiplier,
)

# 2026-10-05 is a Monday
MON = lambda h: datetime(2026, 10, 5, h)  # noqa: E731
FRI = lambda h: datetime(2026, 10, 9, h)  # noqa: E731
SAT = lambda h: datetime(2026, 10, 10, h)  # noqa: E731


def test_score_is_deterministic():
    a = calculate_demand_score(MON(17), "Financial District", "South Station")
    b = calculate_demand_score(MON(17), "Financial District", "South Station")
    assert a == b


def test_score_always_between_0_and_1():
    for day, hour in itertools.product(range(5, 12), range(24)):
        for s, d in itertools.permutations(LOCATION_WEIGHTS, 2):
            assert 0.0 <= calculate_demand_score(datetime(2026, 10, day, hour), s, d) <= 1.0


def test_every_possible_surge_is_a_value_the_model_was_trained_on():
    seen = set()
    for day, hour in itertools.product(range(5, 12), range(24)):
        for s, d in itertools.permutations(LOCATION_WEIGHTS, 2):
            seen.add(calculate_surge_multiplier(calculate_demand_score(datetime(2026, 10, day, hour), s, d)))
    assert seen <= set(ALLOWED_SURGE_VALUES)
    assert 1.0 in seen and len(seen) > 3


@pytest.mark.parametrize("score,expected", [
    (0.0, 1.0), (0.519, 1.0), (0.52, 1.25), (0.619, 1.25), (0.62, 1.5),
    (0.719, 1.5), (0.72, 1.75), (0.799, 1.75), (0.80, 2.0), (0.859, 2.0),
    (0.86, 2.5), (0.949, 2.5), (0.95, 3.0), (1.0, 3.0),
])
def test_surge_thresholds(score, expected):
    assert calculate_surge_multiplier(score) == expected


def test_weekday_rush_hour_beats_weekday_night():
    rush = calculate_demand_score(MON(17), "Financial District", "South Station")
    night = calculate_demand_score(MON(3), "Financial District", "South Station")
    assert rush > night


def test_weekday_midday_has_no_surge():
    assert calculate_surge_multiplier(calculate_demand_score(MON(11), "Fenway", "Back Bay")) == 1.0


def test_weekend_morning_is_quiet_but_weekend_night_is_busy():
    assert calculate_demand_score(SAT(8), "Fenway", "Back Bay") < calculate_demand_score(SAT(22), "Fenway", "Back Bay")


def test_friday_evening_uses_weekend_profile():
    assert calculate_demand_score(FRI(22), "Theatre District", "Fenway") > calculate_demand_score(MON(22), "Theatre District", "Fenway")


def test_busy_location_adds_demand():
    hub = calculate_demand_score(MON(8), "Financial District", "South Station")
    quiet = calculate_demand_score(MON(8), "Northeastern University", "Fenway")
    assert hub > quiet
