"""exact coordinate  ->  Boston neighbourhood  ->  one of the model's location categories.

Two kinds of boundary data (both in app/data/):

1. ``boston_neighborhoods.geojson`` - OFFICIAL City of Boston neighbourhood polygons
   (tract-based, from the BPDA research division). Used for
     a) the service-area check (is the point inside the City of Boston?), and
     b) the direct 1:1 mappings in ``model_area_mapping.json``
        (Back Bay, Beacon Hill, North End, West End, Fenway).

2. ``model_area_refinements.geojson`` - the model also knows areas that are NOT
   official neighbourhoods (Financial District, South Station, North Station,
   Haymarket Square, Theatre District, Boston University, Northeastern University).
   Each one is a street-bounded polygon that only counts INSIDE its listed parent
   official neighbourhoods. Refinements are checked first, so e.g. the BU campus is
   carved out of the official "Fenway" polygon.

A coordinate that is in Boston but in none of these areas is NOT mapped to the
"nearest" category - it is reported as unmapped and the API returns an error.
"""
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from app.errors import LocationNotMappedError, OutsideServiceAreaError
from app.utils.geometry import Shape

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@dataclass(frozen=True)
class AreaMatch:
    in_service_area: bool
    neighborhood: str | None  # official City of Boston neighbourhood, if any
    model_area: str | None  # one of the model's categories, or None
    basis: str | None  # "refinement_polygon" | "official_neighborhood" | None


@dataclass(frozen=True)
class _Refinement:
    model_area: str
    parents: frozenset[str]
    shape: Shape


class LocationMappingService:
    def __init__(
        self,
        neighborhoods: dict[str, Shape],
        refinements: list[_Refinement],
        official_to_model: dict[str, str],
        supported_areas: set[str] | None = None,
    ):
        self._neighborhoods = neighborhoods
        self._refinements = refinements
        self._direct = official_to_model
        boxes = [s.bbox for s in neighborhoods.values()]
        self.bbox = (  # (min_lon, min_lat, max_lon, max_lat) of the whole service area
            min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes),
        )
        self.model_areas = {r.model_area for r in refinements} | set(official_to_model.values())
        if supported_areas is not None:
            missing = supported_areas - self.model_areas
            extra = self.model_areas - supported_areas
            if missing:
                logger.warning("Model categories with NO boundary data (unreachable): %s", sorted(missing))
            if extra:
                logger.warning("Boundary data for categories the model does not know: %s", sorted(extra))

    # ------------------------------------------------------------------ build
    @classmethod
    def from_data_dir(
        cls, data_dir: Path = DATA_DIR, supported_areas: set[str] | None = None
    ) -> "LocationMappingService":
        hoods = json.loads((data_dir / "boston_neighborhoods.geojson").read_text("utf-8"))
        neighborhoods = {
            f["properties"]["name"]: Shape.from_geojson(f["geometry"]) for f in hoods["features"]
        }
        refs = json.loads((data_dir / "model_area_refinements.geojson").read_text("utf-8"))
        refinements = [
            _Refinement(
                model_area=f["properties"]["model_area"],
                parents=frozenset(f["properties"]["parents"]),
                shape=Shape.from_geojson(f["geometry"]),
            )
            for f in refs["features"]
        ]
        direct = json.loads((data_dir / "model_area_mapping.json").read_text("utf-8"))["official_to_model"]
        return cls(neighborhoods, refinements, direct, supported_areas)

    # ----------------------------------------------------------------- lookup
    def locate(self, latitude: float, longitude: float) -> AreaMatch:
        """Never raises. Use ``require_model_area`` for the strict version."""
        names = [n for n, shape in self._neighborhoods.items() if shape.contains(longitude, latitude)]
        if not names:
            return AreaMatch(False, None, None, None)
        hood = names[0]

        for ref in self._refinements:  # specific areas first
            if ref.parents & set(names) and ref.shape.contains(longitude, latitude):
                return AreaMatch(True, hood, ref.model_area, "refinement_polygon")
        for name in names:
            if name in self._direct:
                return AreaMatch(True, name, self._direct[name], "official_neighborhood")
        return AreaMatch(True, hood, None, None)

    def in_service_area(self, latitude: float, longitude: float) -> bool:
        return self.locate(latitude, longitude).in_service_area

    def require_model_area(self, latitude: float, longitude: float, role: str = "location") -> AreaMatch:
        match = self.locate(latitude, longitude)
        if not match.in_service_area:
            raise OutsideServiceAreaError(
                f"The {role} is outside the supported Boston service area."
            )
        if match.model_area is None:
            raise LocationNotMappedError(
                f"The {role} is in {match.neighborhood}, which the fare model does not cover. "
                f"Supported areas: {', '.join(sorted(self.model_areas))}."
            )
        return match
