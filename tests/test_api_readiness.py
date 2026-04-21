from __future__ import annotations

from easy_fints import api
from easy_fints.exceptions import FinTSOperationError
from easy_fints.models import BankInfo, TanMethodsSnapshot
from tests.support.fake_fints_backend import unwrap_response


def test_readiness_returns_ready_payload(monkeypatch):
    def fake_lookup_bank_info(**kwargs):
        assert kwargs["bank"] == "12345678"
        assert kwargs["server"] == "https://bank.example/fints"
        assert kwargs["product_id"] == "demo-product"
        return BankInfo(
            bank_code="12345678",
            server="https://bank.example/fints",
            bank_name="Testbank",
            supported_operations={"GET_SEPA_ACCOUNTS": True},
            supported_formats={},
            supported_sepa_formats=[],
            tan_methods=TanMethodsSnapshot(
                current=None,
                current_name=None,
                methods=[],
                media=None,
            ),
        )

    monkeypatch.setattr(api, "lookup_bank_info", fake_lookup_bank_info)

    status_code, payload = unwrap_response(
        api.readiness(
            {
                "config": {
                    "bank": "12345678",
                    "server": "https://bank.example/fints",
                    "product_id": "demo-product",
                }
            }
        )
    )

    assert status_code == 200
    assert payload["status"] == "ready"
    assert payload["operation"] == "readiness"
    assert payload["reachable"] is True
    assert payload["bank_name"] == "Testbank"


def test_readiness_requires_bank_and_server():
    status_code, payload = unwrap_response(api.readiness({"config": {"server": "https://bank.example/fints"}}))
    assert status_code == 400
    assert payload["field"] == "bank"

    status_code, payload = unwrap_response(api.readiness({"config": {"bank": "12345678"}}))
    assert status_code == 400
    assert payload["field"] == "server"


def test_readiness_returns_not_ready_when_probe_fails(monkeypatch):
    def fake_lookup_bank_info(**kwargs):
        raise FinTSOperationError("bank_info", "bank endpoint unreachable")

    monkeypatch.setattr(api, "lookup_bank_info", fake_lookup_bank_info)

    status_code, payload = unwrap_response(
        api.readiness(
            {
                "config": {
                    "bank": "12345678",
                    "server": "https://bank.example/fints",
                    "product_id": "demo-product",
                }
            }
        )
    )

    assert status_code == 503
    assert payload["status"] == "not_ready"
    assert payload["operation"] == "readiness"
    assert payload["reachable"] is False
    assert payload["message"] == "bank endpoint unreachable"
