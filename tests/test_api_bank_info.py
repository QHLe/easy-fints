from __future__ import annotations

from easy_fints import fastapi_app
from easy_fints.client import _tan_methods_snapshot_from_low_level_client
from easy_fints.models import BankInfo, TanMethod, TanMethodsSnapshot
from tests.support.fake_fints_backend import unwrap_response


def test_bank_info_returns_bankwide_payload(monkeypatch):
    def fake_lookup_bank_info(**kwargs):
        assert kwargs["bank"] == "12345678"
        assert kwargs["server"] == "https://bank.example/fints"
        assert kwargs["product_id"] == "demo-product"
        return BankInfo(
            bank_code="12345678",
            server="https://bank.example/fints",
            bank_name="Testbank",
            supported_operations={
                "GET_SEPA_ACCOUNTS": True,
                "GET_TRANSACTIONS": True,
            },
            supported_formats={
                "SEPA_TRANSFER_SINGLE": ["urn:iso:std:iso:20022:tech:xsd:pain.001.001.03"],
            },
            supported_sepa_formats=["urn:iso:std:iso:20022:tech:xsd:pain.001.001.03"],
            tan_methods=TanMethodsSnapshot(
                current=None,
                current_name=None,
                methods=[
                    TanMethod(
                        code="942",
                        name="pushTAN",
                        security_function="942",
                        identifier="push",
                    )
                ],
                media=None,
            ),
        )

    monkeypatch.setattr(fastapi_app, "lookup_bank_info", fake_lookup_bank_info)

    status_code, payload = unwrap_response(
        fastapi_app.bank_info(
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
    assert payload["bank_name"] == "Testbank"
    assert payload["supported_operations"]["GET_SEPA_ACCOUNTS"] is True
    assert payload["tan_methods"]["methods"][0]["name"] == "pushTAN"


def test_bank_info_requires_bank_and_server():
    status_code, payload = unwrap_response(fastapi_app.bank_info({"config": {"server": "https://bank.example/fints"}}))
    assert status_code == 400
    assert payload["field"] == "bank"

    status_code, payload = unwrap_response(fastapi_app.bank_info({"config": {"bank": "12345678"}}))
    assert status_code == 400
    assert payload["field"] == "server"


def test_anonymous_bank_info_hides_bootstrap_tan_placeholder():
    class _FakeClient:
        def get_tan_mechanisms(self):
            return {}

        def get_current_tan_mechanism(self):
            return "999"

    snapshot = _tan_methods_snapshot_from_low_level_client(_FakeClient())

    assert snapshot.current is None
    assert snapshot.current_name is None
    assert snapshot.methods == []
