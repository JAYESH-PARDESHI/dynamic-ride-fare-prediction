"""TEST FIXTURE ONLY - this is NOT your model.

Builds a small stand-in pipeline with the SAME STRUCTURE as the one in your
notebook (cells 40-51): same step names, same ColumnTransformers, same encoders,
same SelectFromModel + XGBRegressor, same custom DateTimeFeatureTransformer
import path. It is trained on random synthetic data, so its predictions mean
nothing - it only lets the tests prove that the backend feeds a pipeline of
this shape correctly (column names, dtypes, NaN rain, categories...).

Run directly to write one:  python -m tests.dummy_pipeline models/dummy.pkl
"""
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.feature_selection import SelectFromModel
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import (
    OneHotEncoder, OrdinalEncoder, PowerTransformer, RobustScaler, StandardScaler,
)
from xgboost import XGBRegressor

from project.transformer import DateTimeFeatureTransformer

LOCATIONS = [
    "Back Bay", "Beacon Hill", "Boston University", "Fenway", "Financial District",
    "Haymarket Square", "North End", "North Station", "Northeastern University",
    "South Station", "Theatre District", "West End",
]
NAME_ORDER = ["Shared", "UberPool", "Lyft", "UberX", "WAV", "Lyft XL", "UberXL",
              "Lux", "Black", "Lux Black", "Lux Black XL", "Black SUV"]
LYFT = {"Shared", "Lyft", "Lyft XL", "Lux", "Lux Black", "Lux Black XL"}


def make_training_frame(n: int = 3000, seed: int = 0) -> tuple[pd.DataFrame, pd.Series]:
    rng = np.random.default_rng(seed)
    names = rng.choice(NAME_ORDER, n)
    cab = np.where(np.isin(names, list(LYFT)), "Lyft", "Uber")
    start = pd.Timestamp("2018-11-26 03:00:00").value
    end = pd.Timestamp("2018-12-18 18:00:00").value
    date_time = pd.to_datetime(rng.integers(start, end, n))
    rain = np.where(rng.random(n) < 0.2, rng.random(n) * 0.3, np.nan)
    df = pd.DataFrame({
        "distance": rng.uniform(0.3, 5, n).round(2),
        "cab_type": cab,
        "destination": rng.choice(LOCATIONS, n),
        "source": rng.choice(LOCATIONS, n),
        "surge_multiplier": rng.choice([1.0, 1.25, 1.5, 2.0], n, p=[0.9, 0.04, 0.04, 0.02]),
        "name": names,
        "date_time": date_time,
        "temp": rng.uniform(20, 55, n),
        "clouds": rng.random(n),
        "pressure": rng.uniform(990, 1022, n),
        "rain": rain,
        "humidity": rng.uniform(0.4, 1, n),
        "wind": rng.uniform(1, 15, n),
    })
    df["hour_date"] = df["date_time"].dt.floor("h")
    df = df[["distance", "cab_type", "destination", "source", "surge_multiplier", "name",
             "date_time", "hour_date", "temp", "clouds", "pressure", "rain", "humidity", "wind"]]
    tier = df["name"].map({n: i for i, n in enumerate(NAME_ORDER)})
    y = 2.5 + df["distance"] * 2.2 * df["surge_multiplier"] + tier * 1.5 + rng.normal(0, 0.5, n)
    return df, y


def build_dummy_pipeline() -> Pipeline:
    trf1 = ColumnTransformer(
        transformers=[
            ("fill", SimpleImputer(add_indicator=True, fill_value=0, strategy="constant"), ["rain"]),
            ("oe", OrdinalEncoder(categories=[NAME_ORDER], handle_unknown="use_encoded_value",
                                  unknown_value=-1), ["name"]),
            ("ohe", OneHotEncoder(sparse_output=False, drop="first", handle_unknown="ignore"),
             ["cab_type", "destination", "source"]),
        ],
        remainder="passthrough", verbose_feature_names_out=False,
    )
    trf2 = ColumnTransformer(
        transformers=[("pt", PowerTransformer(standardize=False, method="yeo-johnson"),
                       ["distance", "surge_multiplier", "rain"])],
        remainder="passthrough", verbose_feature_names_out=False,
    )
    trf3 = ColumnTransformer(
        transformers=[("rs", RobustScaler(), ["distance", "surge_multiplier", "temp", "rain"]),
                      ("std", StandardScaler(), ["clouds", "pressure", "humidity", "wind"])],
        remainder="passthrough", verbose_feature_names_out=False,
    )
    selector = SelectFromModel(
        estimator=ExtraTreesRegressor(n_estimators=30, random_state=42, n_jobs=-1),
        threshold="median",
    )
    pipe = Pipeline([
        ("date_time_fetures", DateTimeFeatureTransformer()),
        ("tf1", trf1), ("tf2", trf2), ("tf3", trf3),
        ("feature_selection", selector),
        ("model", XGBRegressor(n_estimators=40, learning_rate=0.1, max_depth=4,
                               objective="reg:squarederror", random_state=42, n_jobs=1)),
    ])
    pipe.set_output(transform="pandas")
    X, y = make_training_frame()
    pipe.fit(X, y)
    return pipe


def save_dummy_pipeline(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(build_dummy_pipeline(), path)
    return path


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "dummy_pipeline.pkl")
    print("wrote", save_dummy_pipeline(target))
