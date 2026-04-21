from __future__ import annotations

import asyncio
import datetime as dt

from easy_fints import api
from tests.support.fake_fints_backend import CREATED_CLIENTS, make_transfer_payload, unwrap_response


def test_cancel_active_session_closes_client(fake_backend):
    _, payload = unwrap_response(api.accounts({"config": {"scenario": "accounts_tan"}}))
    session_id = payload["session_id"]

    cancel_status, cancel_payload = unwrap_response(api.cancel_session(session_id))
    assert cancel_status == 200
    assert cancel_payload["status"] == "cancelled"

    assert unwrap_response(api.get_session(session_id))[0] == 404
    assert unwrap_response(api.confirm({"session_id": session_id}))[0] == 404
    assert CREATED_CLIENTS[0].closed is True


def test_session_expiry_prunes_and_closes_client(fake_backend, monkeypatch):
    _, payload = unwrap_response(api.accounts({"config": {"scenario": "accounts_tan"}}))
    session_id = payload["session_id"]

    monkeypatch.setattr(api, "SESSION_TTL", 1)
    api.SESSIONS[session_id]["updated_at"] = dt.datetime.utcnow() - dt.timedelta(seconds=5)

    assert unwrap_response(api.get_session(session_id))[0] == 404
    assert unwrap_response(api.confirm({"session_id": session_id}))[0] == 404
    assert CREATED_CLIENTS[0].closed is True


def test_shutdown_closes_active_clients(fake_backend):
    accounts_status, _ = unwrap_response(api.accounts({"config": {"scenario": "accounts_tan"}}))
    transfer_status, _ = unwrap_response(
        api.transfer(make_transfer_payload(config={"scenario": "transfer_vop_approve"}))
    )

    assert accounts_status == 409
    assert transfer_status == 409
    assert len(api.SESSIONS) == 2

    api.shutdown_active_sessions()

    assert api.SESSIONS == {}
    assert CREATED_CLIENTS
    assert all(client.closed for client in CREATED_CLIENTS)


def test_lifespan_shutdown_closes_active_clients(fake_backend):
    async def run_lifespan() -> None:
        async with api.app.router.lifespan_context(api.app):
            accounts_status, _ = unwrap_response(api.accounts({"config": {"scenario": "accounts_tan"}}))
            transfer_status, _ = unwrap_response(
                api.transfer(make_transfer_payload(config={"scenario": "transfer_vop_approve"}))
            )

            assert accounts_status == 409
            assert transfer_status == 409
            assert len(api.SESSIONS) == 2

    asyncio.run(run_lifespan())

    assert api.SESSIONS == {}
    assert CREATED_CLIENTS
    assert all(client.closed for client in CREATED_CLIENTS)
