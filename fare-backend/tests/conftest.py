import asyncio
from datetime import datetime, timezone

import joblib
import pytest

from app.catalog import ModelCatalog
from app.config import Settings
from app.services.location_mapping_service import LocationMappingService
from app.services.routing_service import Route
from app.services.weather_service import Weather
from tests.dummy_pipeline import save_dummy_pipeline


def run(coro):
    """Run an async function from a plain sync test (no pytest plugin needed)."""
    return asyncio.run(coro)


@pytest.fixture(scope="session")
def dummy_model_path(tmp_path_factory):
    return save_dummy_pipeline(tmp_path_factory.mktemp("model") / "dummy_pipeline.pkl")


@pytest.fixture(scope="session")
def pipeline(dummy_model_path):
    return joblib.load(dummy_model_path)


@pytest.fixture(scope="session")
def catalog(pipeline):
    return ModelCatalog.from_pipeline(pipeline)


@pytest.fixture(scope="session")
def mapper(catalog):
    return LocationMappingService.from_data_dir(supported_areas=set(catalog.sources))


@pytest.fixture
def settings(dummy_model_path):
    return Settings(model_path=str(dummy_model_path), _env_file=None)


class FakeRouting:
    def __init__(self, fail_with=None):
        self.fail_with = fail_with
        self.calls = 0
        self.last_args = None  # (source, destination, include_geometry)

    async def get_route(self, source, destination, include_geometry=False):
        self.calls += 1
        self.last_args = (source, destination, include_geometry)
        if self.fail_with:
            raise self.fail_with
        geometry = None
        if include_geometry:
            geometry = {
                "type": "LineString",
                "coordinates": [
                    [source.longitude, source.latitude],
                    [(source.longitude + destination.longitude) / 2,
                     (source.latitude + destination.latitude) / 2],
                    [destination.longitude, destination.latitude],
                ],
            }
        return Route(
            distance=2.4,
            duration=11.5,
            source_coordinates=(source.latitude, source.longitude),
            destination_coordinates=(destination.latitude, destination.longitude),
            geometry=geometry,
        )


class FakeWeather:
    def __init__(self, rain=None, fail_with=None):
        self.rain = rain
        self.fail_with = fail_with
        self.last_coords = None

    async def get_current_weather(self, latitude, longitude):
        self.last_coords = (latitude, longitude)
        if self.fail_with:
            raise self.fail_with
        return Weather(temp=41.0, clouds=0.75, pressure=1012.0, humidity=0.8, wind=7.5, rain=self.rain)


# Monday 2026-10-05 17:30 Boston time (EDT, UTC-4) = 21:30 UTC
MONDAY_EVENING_UTC = datetime(2026, 10, 5, 21, 30, tzinfo=timezone.utc)


@pytest.fixture
def make_service(pipeline, catalog, settings, mapper):
    from app.services.fare_service import FareService

    def _make(routing=None, weather=None, clock=lambda: MONDAY_EVENING_UTC, cfg=None, pipe=None):
        return FareService(
            pipeline=pipe or pipeline,
            catalog=catalog,
            routing=routing or FakeRouting(),
            weather=weather or FakeWeather(),
            settings=cfg or settings,
            clock=clock,
            mapper=mapper,
        )

    return _make
