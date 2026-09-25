import pytest

from app.service.replay_service import ReplayService
from tests.factories import FakeLiveService, make_replay_day


@pytest.fixture
def replay_service() -> ReplayService:
    return ReplayService(make_replay_day())


@pytest.fixture
def live_service() -> FakeLiveService:
    return FakeLiveService()
