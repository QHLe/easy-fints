from __future__ import annotations

from easy_fints import fastapi_app
from tests.support.fake_fints_backend import unwrap_response


def test_accounts_requires_tan_then_confirm(fake_backend):
    status_code, payload = unwrap_response(fastapi_app.accounts({"config": {"scenario": "accounts_tan"}}))

    assert status_code == 409
    assert payload["error"] == "tan_required"
    assert payload["state"] == "awaiting_tan"

    session_id = payload["session_id"]
    inspect_status, inspect_payload = unwrap_response(fastapi_app.get_session(session_id))
    assert inspect_status == 200
    assert inspect_payload["next_action"] == "provide_tan"

    confirm_status, accounts = unwrap_response(fastapi_app.confirm({"session_id": session_id, "tan": "123456"}))
    assert confirm_status == 200
    assert accounts[0]["iban"] == "DE00123456780000000001"

    assert unwrap_response(fastapi_app.get_session(session_id))[0] == 404


def test_transactions_decoupled_confirmation_loop(fake_backend):
    status_code, payload = unwrap_response(
        fastapi_app.transactions({"config": {"scenario": "transactions_decoupled"}, "days": 5})
    )

    assert status_code == 409
    assert payload["state"] == "awaiting_decoupled"

    session_id = payload["session_id"]
    first_status, first_payload = unwrap_response(fastapi_app.confirm({"session_id": session_id}))
    assert first_status == 202
    assert first_payload["state"] == "awaiting_decoupled"

    second_status, transactions = unwrap_response(fastapi_app.confirm({"session_id": session_id}))
    assert second_status == 200
    assert transactions[0]["transactions"][0]["purpose"] == "Coffee"
