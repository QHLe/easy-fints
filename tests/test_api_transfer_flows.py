from __future__ import annotations

import datetime as dt

from easy_fints import api
from tests.support.fake_fints_backend import CREATED_CLIENTS, make_transfer_payload, unwrap_response


def test_transfer_success_returns_transfer_overview(fake_backend):
    status_code, payload = unwrap_response(api.transfer(make_transfer_payload()))

    assert status_code == 200
    assert payload["success"] is True
    assert payload["transfer_overview"]["recipient_name"] == "Quang Hoa Le"
    assert payload["transfer_overview"]["instant_payment"] is False
    assert payload["transfer_overview"]["execution_date"] is None


def test_transfer_vop_approve_flow(fake_backend):
    status_code, first_payload = unwrap_response(
        api.transfer(make_transfer_payload(config={"scenario": "transfer_vop_approve"}))
    )

    assert status_code == 409
    session_id = first_payload["session_id"]
    assert first_payload["state"] == "awaiting_decoupled"
    assert first_payload["transfer_overview"]["recipient_name"] == "Quang Hoa Le"

    vop_status, vop_payload = unwrap_response(api.confirm({"session_id": session_id}))
    assert vop_status == 409
    assert vop_payload["error"] == "vop_required"
    assert vop_payload["state"] == "awaiting_vop"
    assert vop_payload["vop"]["result"] == "RCVC"

    missing_status, missing_payload = unwrap_response(api.confirm({"session_id": session_id}))
    assert missing_status == 400
    assert missing_payload["field"] == "approve_vop"

    approve_status, approve_payload = unwrap_response(
        api.confirm({"session_id": session_id, "approve_vop": True})
    )
    assert approve_status == 202
    assert approve_payload["state"] == "awaiting_decoupled"

    final_status, final_payload = unwrap_response(api.confirm({"session_id": session_id}))
    assert final_status == 200
    assert final_payload["status"] == "SUCCESS"
    assert final_payload["transfer_overview"]["recipient_name"] == "Quang Hoa Le"


def test_transfer_retry_with_name_reuses_session_and_updates_overview(fake_backend):
    status_code, payload = unwrap_response(
        api.transfer(make_transfer_payload(config={"scenario": "transfer_vop_retry"}))
    )

    assert status_code == 409
    session_id = payload["session_id"]

    vop_status, vop_payload = unwrap_response(api.confirm({"session_id": session_id}))
    assert vop_status == 409
    assert vop_payload["state"] == "awaiting_vop"

    retry_status, retry_payload = unwrap_response(
        api.retry_transfer_with_name(
            {"session_id": session_id, "recipient_name": "Corrected Recipient"}
        )
    )
    assert retry_status == 409
    assert retry_payload["session_id"] == session_id
    assert retry_payload["state"] == "awaiting_decoupled"
    assert retry_payload["transfer_overview"]["recipient_name"] == "Corrected Recipient"

    inspect_status, inspect_payload = unwrap_response(api.get_session(session_id))
    assert inspect_status == 200
    assert inspect_payload["transfer_overview"]["recipient_name"] == "Corrected Recipient"

    final_status, final_payload = unwrap_response(api.confirm({"session_id": session_id}))
    assert final_status == 200
    assert final_payload["success"] is True
    assert final_payload["transfer_overview"]["recipient_name"] == "Corrected Recipient"

    assert len(CREATED_CLIENTS) == 1
    assert CREATED_CLIENTS[0].closed is True


def test_unsupported_instant_payment_is_normalized(fake_backend):
    status_code, payload = unwrap_response(
        api.transfer(
            make_transfer_payload(
                config={"scenario": "transfer_instant_unsupported"},
                instant_payment=True,
            )
        )
    )

    assert status_code == 422
    assert payload["error"] == "unsupported_transfer_product"
    assert payload["product"] == "instant_payment"
    assert payload["instant_payment"] is True


def test_unsupported_scheduled_transfer_is_normalized(fake_backend):
    execution_date = (dt.date.today() + dt.timedelta(days=2)).isoformat()
    status_code, payload = unwrap_response(
        api.transfer(
            make_transfer_payload(
                config={"scenario": "transfer_scheduled_unsupported"},
                execution_date=execution_date,
            )
        )
    )

    assert status_code == 422
    assert payload["error"] == "unsupported_transfer_product"
    assert payload["product"] == "scheduled_transfer"
    assert payload["execution_date"] == execution_date
