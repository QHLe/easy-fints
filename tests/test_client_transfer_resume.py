from __future__ import annotations

from types import SimpleNamespace

from fints_rest_wrapper.client import FinTSClient
from fints_rest_wrapper.models import FinTSConfig, TransferResponse


def _build_client() -> FinTSClient:
    return FinTSClient(
        FinTSConfig(
            product_id="demo-product",
            bank="12345678",
            user="demo-user",
            pin="demo-pin",
            server="https://bank.example/fints",
        )
    )


def test_finalize_pending_transfer_result_maps_transaction_response():
    client = _build_client()
    client._remember_pending_transfer(
        {
            "source_account": "DE00123456780000000000",
            "account_name": "Max Mustermann",
            "recipient_name": "Erika Musterfrau",
            "recipient_iban": "DE02120300000000202051",
            "recipient_bic": "BYLADEM1001",
            "amount": "12.34",
            "purpose": "Test",
            "endtoend_id": "NOTPROVIDED",
            "instant_payment": False,
            "execution_date": None,
        },
        transfer_overview={
            "source_account_label": "DE51500105175448773293",
        },
    )

    result = client._finalize_pending_transfer_result(
        SimpleNamespace(
            status=SimpleNamespace(name="SUCCESS"),
            responses=[SimpleNamespace(code="0010", text="Order accepted.", reference="ABC123")],
        )
    )

    assert isinstance(result, TransferResponse)
    assert result.success is True
    assert result.source_account_label == "DE51500105175448773293"
    assert result.reference == "ABC123"
    assert client._pending_transfer_params is None


def test_finalize_pending_transfer_result_retries_operation_when_result_is_not_transfer(monkeypatch):
    client = _build_client()
    client._remember_pending_transfer(
        {
            "source_account": "DE00123456780000000000",
            "account_name": "Max Mustermann",
            "recipient_name": "Erika Musterfrau",
            "recipient_iban": "DE02120300000000202051",
            "recipient_bic": "BYLADEM1001",
            "amount": "12.34",
            "purpose": "Test",
            "endtoend_id": "NOTPROVIDED",
            "instant_payment": False,
            "execution_date": None,
        }
    )

    captured: dict[str, object] = {}

    def fake_initiate_transfer(**kwargs):
        captured.update(kwargs)
        return "retried-transfer"

    monkeypatch.setattr(client, "initiate_transfer", fake_initiate_transfer)

    result = client._finalize_pending_transfer_result(object())

    assert result == "retried-transfer"
    assert captured["recipient_name"] == "Erika Musterfrau"
    assert client._pending_transfer_params is None
