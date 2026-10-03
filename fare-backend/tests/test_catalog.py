import pytest

from app.errors import InvalidRideOptionError, UnsupportedLocationError

EXPECTED = {
    "Back Bay", "Beacon Hill", "Boston University", "Fenway", "Financial District",
    "Haymarket Square", "North End", "North Station", "Northeastern University",
    "South Station", "Theatre District", "West End",
}


def test_locations_come_from_the_pipeline_encoder(catalog):
    assert set(catalog.sources) == EXPECTED
    assert set(catalog.destinations) == EXPECTED


def test_resolve_exact_case_and_spacing_insensitive(catalog):
    assert catalog.resolve_location("  beacon   hill ", "source").name == "Beacon Hill"


def test_resolve_alias(catalog):
    assert catalog.resolve_location("BU", "destination").name == "Boston University"


@pytest.mark.parametrize("bad", ["Cambridge", "Logan Airport", "123 Main St", "Beacon", "Boston"])
def test_unsupported_location_is_rejected_not_guessed(catalog, bad):
    with pytest.raises(UnsupportedLocationError) as err:
        catalog.resolve_location(bad, "source")
    assert "not supported by the currently trained model" in err.value.message
    assert "Beacon Hill" in err.value.message  # lists what IS supported


def test_valid_ride_option(catalog):
    assert catalog.validate_ride_option("uber", "uberx") == ("Uber", "UberX")
    assert catalog.validate_ride_option("Lyft", "lux black xl") == ("Lyft", "Lux Black XL")


@pytest.mark.parametrize("cab,name", [
    ("Ola", "UberX"), ("Uber", "Lux"), ("Lyft", "UberX"), ("Uber", "Taxi"), ("Uber", "Lyft"),
])
def test_invalid_cab_or_ride_name(catalog, cab, name):
    with pytest.raises(InvalidRideOptionError):
        catalog.validate_ride_option(cab, name)
