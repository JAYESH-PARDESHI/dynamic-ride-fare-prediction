"""exact coordinate -> Boston neighbourhood -> model category.

NOTE: the 7 refinement areas (FiDi, South/North Station, Haymarket, Theatre District, BU,
Northeastern) are street-bounded polygons authored in app/data/model_area_refinements.geojson.
These tests pin the landmarks those polygons are meant to cover; they check the data file
against intent, not against an official source.
"""
import pytest

from app.errors import LocationNotMappedError, OutsideServiceAreaError
from app.services.location_mapping_service import LocationMappingService

LANDMARKS = [
    # (name, lat, lon, expected model area)
    ("Copley Square", 42.3500, -71.0773, "Back Bay"),
    ("Boston Public Library", 42.3493, -71.0782, "Back Bay"),
    ("Prudential Center", 42.3472, -71.0820, "Back Bay"),
    ("Fenway Park", 42.3467, -71.0972, "Fenway"),
    ("Kenmore Square", 42.3489, -71.0953, "Fenway"),
    ("Massachusetts State House", 42.3587, -71.0637, "Beacon Hill"),
    ("Boston Common", 42.3550, -71.0655, "Beacon Hill"),
    ("Paul Revere House", 42.3637, -71.0537, "North End"),
    ("Mass General Hospital", 42.3631, -71.0686, "West End"),
    ("BU Marsh Chapel", 42.3505, -71.1054, "Boston University"),
    ("Northeastern Snell Library", 42.3384, -71.0883, "Northeastern University"),
    ("South Station", 42.3519, -71.0552, "South Station"),
    ("TD Garden", 42.3663, -71.0622, "North Station"),
    ("Haymarket", 42.3629, -71.0583, "Haymarket Square"),
    ("Post Office Square", 42.3556, -71.0553, "Financial District"),
    ("Colonial Theatre", 42.3523, -71.0656, "Theatre District"),
]


@pytest.mark.parametrize("name,lat,lon,expected", LANDMARKS, ids=[l[0] for l in LANDMARKS])
def test_landmark_maps_to_expected_model_area(mapper, name, lat, lon, expected):
    match = mapper.require_model_area(lat, lon)
    assert match.model_area == expected
    assert match.in_service_area


def test_copley_square_is_back_bay_from_official_boundary(mapper):
    m = mapper.locate(42.3500, -71.0773)
    assert (m.neighborhood, m.model_area, m.basis) == ("Back Bay", "Back Bay", "official_neighborhood")


def test_fenway_park_is_fenway(mapper):
    assert mapper.locate(42.3467, -71.0972).model_area == "Fenway"


def test_campuses_are_carved_out_of_the_official_fenway_polygon(mapper):
    m = mapper.locate(42.3505, -71.1054)  # BU
    assert m.neighborhood == "Fenway"  # official neighbourhood...
    assert m.model_area == "Boston University" and m.basis == "refinement_polygon"  # ...refined


def test_inside_boston_but_not_covered_by_model_is_unmapped_not_nearest(mapper):
    # Jamaica Plain, Faneuil Hall and Downtown Crossing are in Boston, but none of the
    # model's 12 areas covers them -> error, never "closest category".
    for lat, lon in [(42.3099, -71.1130), (42.3600, -71.0568), (42.3555, -71.0603)]:
        match = mapper.locate(lat, lon)
        assert match.in_service_area and match.model_area is None
        with pytest.raises(LocationNotMappedError) as exc:
            mapper.require_model_area(lat, lon, "pickup location")
        assert "does not cover" in exc.value.message


@pytest.mark.parametrize("lat,lon", [
    (42.3736, -71.1190),   # Harvard Square, Cambridge
    (42.3500, -71.0300),   # Boston Harbor (water)
    (42.3565, -71.1050),   # Charles River
    (40.7128, -74.0060),   # New York City
])
def test_outside_service_area(mapper, lat, lon):
    assert mapper.locate(lat, lon).in_service_area is False
    with pytest.raises(OutsideServiceAreaError):
        mapper.require_model_area(lat, lon, "pickup location")


def test_refinement_only_applies_inside_its_parent_neighbourhood(mapper):
    # Chinatown gate sits next to the Theatre District box but is excluded from it.
    assert mapper.locate(42.3512, -71.0624).model_area is None


def test_every_model_category_has_boundary_data(catalog):
    m = LocationMappingService.from_data_dir(supported_areas=set(catalog.sources))
    assert m.model_areas == set(catalog.sources) == set(catalog.destinations)


def test_each_refinement_polygon_actually_hits_its_parent():
    """Guards against a typo'd parent name making a refinement unreachable."""
    m = LocationMappingService.from_data_dir()
    for ref in m._refinements:
        x0, y0, x1, y1 = ref.shape.bbox
        centre = ((x0 + x1) / 2, (y0 + y1) / 2)
        hits = {n for n, s in m._neighborhoods.items() if s.contains(*centre)}
        assert ref.parents & hits, f"{ref.model_area}: centre is not inside any parent {ref.parents}"
        assert ref.parents <= set(m._neighborhoods), f"unknown parent in {ref.model_area}"
