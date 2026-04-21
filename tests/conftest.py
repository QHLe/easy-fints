from __future__ import annotations

import pytest

from easy_fints import api
from tests.support.fake_fints_backend import CREATED_CLIENTS, FakeFinTSClient


@pytest.fixture()
def fake_backend(monkeypatch):
    CREATED_CLIENTS.clear()
    api.shutdown_active_sessions()
    api.SESSIONS.clear()
    monkeypatch.setattr(api.FinTSClient, "from_env", FakeFinTSClient.from_env)
    monkeypatch.setattr(api, "SESSION_TTL", 300)
    yield
    api.shutdown_active_sessions()
    api.SESSIONS.clear()
    CREATED_CLIENTS.clear()
