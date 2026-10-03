"""Print what the saved pipeline expects, and run one sample prediction.

Usage (from the backend root folder):
    python -m scripts.inspect_pipeline
    python -m scripts.inspect_pipeline path/to/other.pkl
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.catalog import LOCATION_COORDINATES, ModelCatalog
from app.config import get_settings
from app.model_loader import load_pipeline
from app.services.fare_service import build_model_input
from app.services.routing_service import Route
from app.services.weather_service import Weather


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else get_settings().resolved_model_path
    pipe = load_pipeline(path)

    print("\nSTEPS:", [name for name, _ in pipe.steps])
    tf1 = pipe.named_steps["tf1"]
    print("\nColumns the first ColumnTransformer was fitted on:")
    print("  ", list(tf1.feature_names_in_))

    ohe = tf1.named_transformers_["ohe"]
    print("\nOneHotEncoder: handle_unknown =", ohe.handle_unknown, "| drop =", ohe.drop)
    for col, cats, idx in zip(ohe.feature_names_in_, ohe.categories_, ohe.drop_idx_):
        print(f"  {col}: {len(cats)} categories; dropped baseline = {cats[idx]!r}")
        print("     ", list(cats))
    oe = tf1.named_transformers_["oe"]
    print("\nOrdinalEncoder (name):", list(oe.categories_[0]), "| unknown ->", oe.unknown_value)

    catalog = ModelCatalog.from_pipeline(pipe)
    no_coords = (set(catalog.sources) | set(catalog.destinations)) - set(LOCATION_COORDINATES)
    print("\nLocations without coordinates in app/catalog.py:", sorted(no_coords) or "none")

    # One sample prediction through exactly the code path the API uses.
    src = catalog.resolve_location(catalog.sources[1], "source")
    dst = catalog.resolve_location(catalog.destinations[4], "destination")
    cab, ride = catalog.validate_ride_option("Uber", "UberX")
    frame = build_model_input(
        route=Route(2.4, 10.0, (src.latitude, src.longitude), (dst.latitude, dst.longitude)),
        weather=Weather(temp=40.0, clouds=0.7, pressure=1012.0, humidity=0.75, wind=8.0, rain=None),
        source=src, destination=dst, cab_type=cab, ride_name=ride,
        surge_multiplier=1.0, now_utc=datetime.now(timezone.utc),
    )
    print("\nSample input row:\n", frame.T.to_string())
    print("\nSample prediction:", float(pipe.predict(frame)[0]))


if __name__ == "__main__":
    main()
