"""Clock helpers.

TWO different clocks are used on purpose:

1. MODEL clock (UTC)
   In the training notebook, ``date_time = pd.to_datetime(time_stamp, unit="ms")``.
   That produces a *UTC* timestamp, so the model's ``hour`` / ``is_rush_hour`` /
   ``hour_sin`` / ``hour_cos`` features were learned on UTC hours. To feed the
   model the same kind of values it was trained on, we also send UTC.

2. DEMAND clock (Boston local time)
   The simulated demand/surge logic is about what a rider in Boston would
   experience (morning rush, Friday night...), so it uses America/New_York.

The pipeline itself derives hour/day_of_week/day/... from ``date_time``. We
only supply ``date_time`` and ``hour_date`` (the training frame had both).
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd

BOSTON_TZ = ZoneInfo("America/New_York")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_model_clock(now_utc: datetime, mode: str = "utc") -> tuple[pd.Timestamp, pd.Timestamp]:
    """Return (date_time, hour_date) as naive timestamps for the model.

    mode="utc"    (default) naive UTC, exactly like the training data.
    mode="boston" naive Boston wall-clock time (MODEL_CLOCK=boston in .env).
    """
    if mode == "boston":
        naive = pd.Timestamp(to_boston(now_utc).replace(tzinfo=None))
    else:
        naive = pd.Timestamp(now_utc.astimezone(timezone.utc).replace(tzinfo=None))
    return naive, naive.floor("h")


def to_boston(now_utc: datetime) -> datetime:
    return now_utc.astimezone(BOSTON_TZ)
