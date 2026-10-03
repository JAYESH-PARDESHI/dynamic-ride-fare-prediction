"""Loads the saved pipeline ONCE at startup."""
import importlib
import logging
from pathlib import Path

import joblib
from sklearn.pipeline import Pipeline

from app.errors import ModelLoadError

logger = logging.getLogger(__name__)

# Module the pickle expects (see scripts/inspect_pipeline.py / README).
TRANSFORMER_MODULE = "project.transformer"
TRANSFORMER_CLASS = "DateTimeFeatureTransformer"


def verify_transformer_importable() -> None:
    try:
        module = importlib.import_module(TRANSFORMER_MODULE)
        getattr(module, TRANSFORMER_CLASS)
    except Exception as exc:  # ImportError / AttributeError / anything in the module
        raise ModelLoadError(
            f"Cannot import {TRANSFORMER_MODULE}.{TRANSFORMER_CLASS}, which the pickle needs. "
            "Make sure the 'project/' folder (with __init__.py and transformer.py) is in the "
            "backend root and that you start uvicorn from that root folder. "
            f"Details: {type(exc).__name__}: {exc}"
        ) from exc


def load_pipeline(path: Path) -> Pipeline:
    verify_transformer_importable()

    if not path.is_file():
        raise ModelLoadError(
            f"Model file not found at '{path}'. Put fare_prediction_pipeline.pkl in the "
            "'models/' folder or set MODEL_PATH in .env."
        )
    try:
        pipeline = joblib.load(path)
    except Exception as exc:
        raise ModelLoadError(
            f"Failed to unpickle '{path.name}'. This is usually a library-version mismatch "
            "(scikit-learn / xgboost / pandas / numpy must match the versions used for "
            f"training - see requirements.txt). Details: {type(exc).__name__}: {exc}"
        ) from exc

    if not isinstance(pipeline, Pipeline) or not hasattr(pipeline, "predict"):
        raise ModelLoadError(f"'{path.name}' did not contain a scikit-learn Pipeline.")

    logger.info("Loaded pipeline from %s (steps: %s)", path, [n for n, _ in pipeline.steps])
    return pipeline
