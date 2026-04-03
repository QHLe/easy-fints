from __future__ import annotations

import pytest

from src import fastapi_app
from tests.support.fake_fints_backend import CREATED_CLIENTS, FakePyFinIntegrationClient


@pytest.fixture()
def fake_backend(monkeypatch):
    CREATED_CLIENTS.clear()
    fastapi_app.shutdown_active_sessions()
    fastapi_app.SESSIONS.clear()
    monkeypatch.setattr(fastapi_app.PyFinIntegrationClient, "from_env", FakePyFinIntegrationClient.from_env)
    monkeypatch.setattr(fastapi_app, "SESSION_TTL", 300)
    yield
    fastapi_app.shutdown_active_sessions()
    fastapi_app.SESSIONS.clear()
    CREATED_CLIENTS.clear()
