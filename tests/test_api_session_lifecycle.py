from __future__ import annotations

import datetime as dt

from src import fastapi_app
from tests.support.fake_fints_backend import CREATED_CLIENTS, make_transfer_payload, unwrap_response


def test_cancel_active_session_closes_client(fake_backend):
    _, payload = unwrap_response(fastapi_app.accounts({"config": {"scenario": "accounts_tan"}}))
    session_id = payload["session_id"]

    cancel_status, cancel_payload = unwrap_response(fastapi_app.cancel_session(session_id))
    assert cancel_status == 200
    assert cancel_payload["status"] == "cancelled"

    assert unwrap_response(fastapi_app.get_session(session_id))[0] == 404
    assert unwrap_response(fastapi_app.confirm({"session_id": session_id}))[0] == 404
    assert CREATED_CLIENTS[0].closed is True


def test_session_expiry_prunes_and_closes_client(fake_backend, monkeypatch):
    _, payload = unwrap_response(fastapi_app.accounts({"config": {"scenario": "accounts_tan"}}))
    session_id = payload["session_id"]

    monkeypatch.setattr(fastapi_app, "SESSION_TTL", 1)
    fastapi_app.SESSIONS[session_id]["updated_at"] = dt.datetime.utcnow() - dt.timedelta(seconds=5)

    assert unwrap_response(fastapi_app.get_session(session_id))[0] == 404
    assert unwrap_response(fastapi_app.confirm({"session_id": session_id}))[0] == 404
    assert CREATED_CLIENTS[0].closed is True


def test_shutdown_closes_active_clients(fake_backend):
    accounts_status, _ = unwrap_response(fastapi_app.accounts({"config": {"scenario": "accounts_tan"}}))
    transfer_status, _ = unwrap_response(
        fastapi_app.transfer(make_transfer_payload(config={"scenario": "transfer_vop_approve"}))
    )

    assert accounts_status == 409
    assert transfer_status == 409
    assert len(fastapi_app.SESSIONS) == 2

    fastapi_app.shutdown_active_sessions()

    assert fastapi_app.SESSIONS == {}
    assert CREATED_CLIENTS
    assert all(client.closed for client in CREATED_CLIENTS)
