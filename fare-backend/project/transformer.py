"""DateTimeFeatureTransformer - first step of the saved fare pipeline.

IMPORTANT
---------
The pickle contains only the *name* of this class, not its code. When the
backend loads the pipeline, THIS file's ``transform`` method is what actually
runs. If you still have the original ``project/transformer.py`` from your
notebook project, copy it over this file - your original is the authority.

This version is reconstructed from your description plus what the fitted
pipeline revealed about its own input: the next pipeline step (``tf1``) was
fitted on the columns below, which do NOT include ``date_time`` or
``hour_date``. So the original transformer must drop those two columns after
deriving the time features, and this one does the same.
"""
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin

RUSH_HOURS = [8, 9, 17, 18, 19]
NEW_COLUMNS = [
    "hour", "day_of_week", "day", "month",
    "is_weekend", "is_rush_hour", "hour_sin", "hour_cos",
]
DROPPED_COLUMNS = ["date_time", "hour_date"]


class DateTimeFeatureTransformer(BaseEstimator, TransformerMixin):
    def __init__(self):
        pass

    def fit(self, X, y=None):
        if hasattr(X, "columns"):
            self.feature_names_in_ = np.asarray(X.columns, dtype=object)
        return self

    def get_feature_names_out(self, input_features=None):
        # Needed so that Pipeline.set_output(transform="pandas") works - your
        # notebook called it, so your original class must have had this method.
        if input_features is None:
            input_features = getattr(self, "feature_names_in_", None)
        if input_features is None:
            raise ValueError("input_features is required")
        kept = [c for c in input_features if c not in DROPPED_COLUMNS]
        return np.asarray(kept + NEW_COLUMNS, dtype=object)

    def transform(self, X):
        X = X.copy()

        X["date_time"] = pd.to_datetime(X["date_time"])

        X["hour"] = X["date_time"].dt.hour
        X["day_of_week"] = X["date_time"].dt.dayofweek
        X["day"] = X["date_time"].dt.day
        X["month"] = X["date_time"].dt.month

        X["is_weekend"] = X["day_of_week"].isin([5, 6]).astype(int)
        X["is_rush_hour"] = X["hour"].isin(RUSH_HOURS).astype(int)

        X["hour_sin"] = np.sin(2 * np.pi * X["hour"] / 24)
        X["hour_cos"] = np.cos(2 * np.pi * X["hour"] / 24)

        # Not seen by the next pipeline step during training (see module docstring).
        return X.drop(columns=DROPPED_COLUMNS, errors="ignore")
