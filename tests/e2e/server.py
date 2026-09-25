"""Deterministic full-stack server used only by Playwright."""
from app import api as api_module
from app.service.replay_service import ReplayService
from tests.factories import FakeLiveService, make_replay_day

api_module._replay = api_module.Lazy(
    "replay", lambda: ReplayService(make_replay_day()), "test fixture unavailable"
)
api_module._live = api_module.Lazy("live", FakeLiveService, "test fixture unavailable")

app = api_module.app
