"""Small, dependency-free point-in-polygon helpers (GeoJSON order: [lon, lat]).

Boston's boundaries are a few thousand vertices, and a lookup runs a bounding-box
pre-check first, so plain ray casting is plenty fast and avoids a GIS dependency.
"""
from dataclasses import dataclass

Ring = list[list[float]]  # [[lon, lat], ...]
Polygon = list[Ring]  # [outer_ring, *hole_rings]


def _in_ring(lon: float, lat: float, ring: Ring) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


@dataclass(frozen=True)
class Shape:
    """A (Multi)Polygon with a cached bounding box."""

    polygons: tuple[tuple[Polygon, tuple[float, float, float, float]], ...]

    @classmethod
    def from_geojson(cls, geometry: dict) -> "Shape":
        kind = geometry["type"]
        if kind == "Polygon":
            polys = [geometry["coordinates"]]
        elif kind == "MultiPolygon":
            polys = geometry["coordinates"]
        else:
            raise ValueError(f"Unsupported geometry type: {kind}")
        return cls(tuple((p, _bbox(p[0])) for p in polys))

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        """(min_lon, min_lat, max_lon, max_lat)"""
        boxes = [b for _, b in self.polygons]
        return (
            min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes),
        )

    def contains(self, lon: float, lat: float) -> bool:
        for poly, (x0, y0, x1, y1) in self.polygons:
            if not (x0 <= lon <= x1 and y0 <= lat <= y1):
                continue
            if _in_ring(lon, lat, poly[0]) and not any(_in_ring(lon, lat, h) for h in poly[1:]):
                return True
        return False


def _bbox(ring: Ring) -> tuple[float, float, float, float]:
    lons = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    return min(lons), min(lats), max(lons), max(lats)
