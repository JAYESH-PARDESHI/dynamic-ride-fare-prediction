"""Simulated demand -> surge multiplier.

THIS IS A PROJECT-SPECIFIC SIMULATION. It is NOT Uber's/Lyft's surge algorithm,
and it uses no real-time demand data (your dataset has none).

Flow (everything is known BEFORE the fare is predicted - no target leakage):

    Boston local time + source/destination
            |
            v
    calculate_demand_score()      -> number between 0.0 and 1.0
            |
            v
    calculate_surge_multiplier()  -> one of 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0
            |
            v
    existing ML pipeline (surge_multiplier is a normal input column)

The score is deterministic: same inputs -> same score.

How the score is built (all numbers are tunable below):
  1. TIME PROFILE   : a typical "how busy is this hour" value (0-1) for each hour
                      of the day, with one profile for weekdays and one for weekends.
                      Friday from 18:00 on uses the weekend profile.
  2. LOCATION BONUS : each neighbourhood has a "commute" weight (office/transport hubs)
                      and a "leisure" weight (nightlife/events/students).
                      Commute weight counts during weekday rush windows, leisure weight
                      counts in the evening/night. Pickup area counts fully,
                      drop-off area counts half.
  3. score = time_profile + location_bonus   (capped to 0-1)
"""
from datetime import datetime

# The only values the trained model has seen for surge_multiplier.
ALLOWED_SURGE_VALUES: tuple[float, ...] = (1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0)

# (minimum score, surge multiplier) - checked from the highest score downwards.
SURGE_THRESHOLDS: tuple[tuple[float, float], ...] = (
    (0.95, 3.0),
    (0.86, 2.5),
    (0.80, 2.0),
    (0.72, 1.75),
    (0.62, 1.5),
    (0.52, 1.25),
    (0.00, 1.0),
)

# Hour of day (Boston local time, index 0 = midnight..1am) -> typical busyness.
WEEKDAY_PROFILE: tuple[float, ...] = (
    0.20, 0.15, 0.10, 0.10, 0.15, 0.25,   # 00-05
    0.42, 0.58, 0.64, 0.52, 0.40, 0.40,   # 06-11  morning peak 07-09
    0.45, 0.42, 0.40, 0.46, 0.58, 0.66,   # 12-17  evening build-up
    0.62, 0.52, 0.42, 0.38, 0.35, 0.28,   # 18-23  evening peak 17-18
)
WEEKEND_PROFILE: tuple[float, ...] = (
    0.64, 0.62, 0.50, 0.25, 0.10, 0.10,   # 00-05  late-night going-home peak
    0.12, 0.15, 0.20, 0.28, 0.38, 0.45,   # 06-11
    0.50, 0.50, 0.48, 0.48, 0.52, 0.56,   # 12-17
    0.62, 0.66, 0.70, 0.72, 0.74, 0.70,   # 18-23  evening / nightlife peak
)

# (commute weight, leisure weight), each 0-1.
LOCATION_WEIGHTS: dict[str, tuple[float, float]] = {
    "Financial District": (1.0, 0.3),
    "South Station": (1.0, 0.3),
    "North Station": (0.9, 0.7),
    "Back Bay": (0.8, 0.6),
    "Haymarket Square": (0.5, 0.5),
    "West End": (0.5, 0.6),
    "Beacon Hill": (0.4, 0.5),
    "North End": (0.3, 0.9),
    "Theatre District": (0.3, 1.0),
    "Fenway": (0.3, 0.9),
    "Boston University": (0.3, 0.7),
    "Northeastern University": (0.3, 0.6),
}
DEFAULT_WEIGHTS = (0.4, 0.4)

SOURCE_BONUS_MAX = 0.08
DESTINATION_BONUS_MAX = 0.04


def _uses_weekend_profile(local_time: datetime) -> bool:
    weekday = local_time.weekday()  # Monday=0 ... Sunday=6
    return weekday in (5, 6) or (weekday == 4 and local_time.hour >= 18)


def _is_commute_window(local_time: datetime) -> bool:
    return local_time.weekday() <= 4 and local_time.hour in (7, 8, 9, 16, 17, 18)


def _is_leisure_window(local_time: datetime) -> bool:
    return local_time.hour >= 18 or local_time.hour < 3


def _location_factor(location: str, local_time: datetime) -> float:
    commute, leisure = LOCATION_WEIGHTS.get(location, DEFAULT_WEIGHTS)
    factor = 0.0
    if _is_commute_window(local_time):
        factor = max(factor, commute)
    if _is_leisure_window(local_time):
        factor = max(factor, leisure)
    return factor


def calculate_demand_score(local_time: datetime, source: str, destination: str) -> float:
    """Return a deterministic simulated demand score in [0.0, 1.0].

    ``local_time`` must be Boston local time.
    """
    profile = WEEKEND_PROFILE if _uses_weekend_profile(local_time) else WEEKDAY_PROFILE
    base = profile[local_time.hour]
    bonus = (
        SOURCE_BONUS_MAX * _location_factor(source, local_time)
        + DESTINATION_BONUS_MAX * _location_factor(destination, local_time)
    )
    return round(min(1.0, max(0.0, base + bonus)), 3)


def calculate_surge_multiplier(demand_score: float) -> float:
    """Map a demand score to one of the discrete values the model was trained on."""
    for minimum, surge in SURGE_THRESHOLDS:
        if demand_score >= minimum:
            return surge
    return 1.0
