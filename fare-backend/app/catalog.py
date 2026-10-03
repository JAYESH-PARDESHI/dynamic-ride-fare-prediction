"""What the TRAINED MODEL supports: locations, cab types, ride options.

The lists of valid values are read from the fitted pipeline's own encoders at
startup (see ``ModelCatalog.from_pipeline``), so they always match the pickle.

Why strict validation? The pipeline's OneHotEncoder uses ``drop="first"`` +
``handle_unknown="ignore"``. An unknown value would become all-zeros, which is
EXACTLY how the dropped baseline category ("Back Bay" / "Lyft") is encoded - so
an unknown source would silently be priced as Back Bay. We refuse instead.
"""
import logging
from dataclasses import dataclass

from app.errors import (
    InvalidRideOptionError,
    ModelLoadError,
    UnsupportedLocationError,
)

logger = logging.getLogger(__name__)

# Approximate neighbourhood centre points (latitude, longitude). The model was
# trained on neighbourhood-level categories, so these stand in for geocoding.
LOCATION_COORDINATES: dict[str, tuple[float, float]] = {
    "Back Bay": (42.3503, -71.0810),
    "Beacon Hill": (42.3588, -71.0707),
    "Boston University": (42.3505, -71.1054),
    "Fenway": (42.3467, -71.0972),
    "Financial District": (42.3559, -71.0550),
    "Haymarket Square": (42.3629, -71.0583),
    "North End": (42.3647, -71.0542),
    "North Station": (42.3663, -71.0622),
    "Northeastern University": (42.3398, -71.0892),
    "South Station": (42.3519, -71.0552),
    "Theatre District": (42.3510, -71.0645),
    "West End": (42.3646, -71.0661),
}

# Convenience spellings -> canonical name. Anything else must match exactly
# (ignoring case / extra spaces). Nothing is guessed or "closest-matched".
LOCATION_ALIASES: dict[str, str] = {
    "bu": "Boston University",
    "northeastern": "Northeastern University",
    "neu": "Northeastern University",
    "fidi": "Financial District",
    "haymarket": "Haymarket Square",
    "theater district": "Theatre District",
}

# Which ride options belong to which company (from the Boston Uber/Lyft dataset).
RIDE_OPTIONS_BY_CAB: dict[str, tuple[str, ...]] = {
    "Lyft": ("Shared", "Lyft", "Lyft XL", "Lux", "Lux Black", "Lux Black XL"),
    "Uber": ("UberPool", "UberX", "WAV", "UberXL", "Black", "Black SUV"),
}


def _norm(text: str) -> str:
    return " ".join(text.split()).casefold()


@dataclass(frozen=True)
class Location:
    name: str
    latitude: float
    longitude: float


@dataclass(frozen=True)
class ModelCatalog:
    sources: tuple[str, ...]
    destinations: tuple[str, ...]
    cab_types: tuple[str, ...]
    ride_names: tuple[str, ...]

    # ------------------------------------------------------------------ build
    @classmethod
    def from_pipeline(cls, pipeline) -> "ModelCatalog":
        try:
            tf1 = pipeline.named_steps["tf1"]
            ohe = tf1.named_transformers_["ohe"]
            oe = tf1.named_transformers_["oe"]
            ohe_cols = list(ohe.feature_names_in_)
            oe_cols = list(oe.feature_names_in_)
            by_col = dict(zip(ohe_cols, ohe.categories_))
            names = tuple(str(x) for x in oe.categories_[oe_cols.index("name")])
            catalog = cls(
                sources=tuple(str(x) for x in by_col["source"]),
                destinations=tuple(str(x) for x in by_col["destination"]),
                cab_types=tuple(str(x) for x in by_col["cab_type"]),
                ride_names=names,
            )
        except (KeyError, AttributeError, ValueError) as exc:
            raise ModelLoadError(
                "The saved pipeline does not have the expected structure "
                "(step 'tf1' with transformers 'ohe' [cab_type, destination, source] "
                f"and 'oe' [name]). Details: {type(exc).__name__}: {exc}"
            ) from exc

        catalog._warn_on_gaps()
        return catalog

    def _warn_on_gaps(self) -> None:
        missing_coords = [
            loc for loc in set(self.sources) | set(self.destinations)
            if loc not in LOCATION_COORDINATES
        ]
        if missing_coords:
            logger.warning("No coordinates configured for model locations: %s", missing_coords)
        known = {n for names in RIDE_OPTIONS_BY_CAB.values() for n in names}
        unmapped = [n for n in self.ride_names if n not in known]
        if unmapped:
            logger.warning("Ride names in the model with no cab_type mapping: %s", unmapped)

    # --------------------------------------------------------------- resolve
    def resolve_location(self, text: str, role: str) -> Location:
        """role is 'source' or 'destination'. Raises UnsupportedLocationError."""
        allowed = self.sources if role == "source" else self.destinations
        wanted = _norm(text)
        wanted = _norm(LOCATION_ALIASES.get(wanted, wanted))
        for name in allowed:
            if _norm(name) == wanted and name in LOCATION_COORDINATES:
                lat, lon = LOCATION_COORDINATES[name]
                return Location(name=name, latitude=lat, longitude=lon)
        raise UnsupportedLocationError(
            f"The {role} '{text.strip()}' is not supported by the currently trained model. "
            f"Supported {role} locations: {', '.join(sorted(allowed))}."
        )

    def validate_ride_option(self, cab_type: str, name: str) -> tuple[str, str]:
        """Return canonical (cab_type, name) or raise InvalidRideOptionError."""
        cab = next((c for c in self.cab_types if _norm(c) == _norm(cab_type)), None)
        if cab is None:
            raise InvalidRideOptionError(
                f"Unsupported cab_type '{cab_type.strip()}'. "
                f"Supported: {', '.join(sorted(self.cab_types))}."
            )
        options = [n for n in RIDE_OPTIONS_BY_CAB.get(cab, ()) if n in self.ride_names]
        ride = next((n for n in options if _norm(n) == _norm(name)), None)
        if ride is None:
            raise InvalidRideOptionError(
                f"'{name.strip()}' is not a valid ride option for {cab}. "
                f"Valid {cab} options: {', '.join(options)}."
            )
        return cab, ride

    # ----------------------------------------------------------- for clients
    def describe(self) -> dict:
        return {
            "sources": sorted(self.sources),
            "destinations": sorted(self.destinations),
            "cab_types": {
                cab: [n for n in opts if n in self.ride_names]
                for cab, opts in RIDE_OPTIONS_BY_CAB.items()
                if cab in self.cab_types
            },
        }
