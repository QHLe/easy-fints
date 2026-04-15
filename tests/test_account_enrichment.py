from __future__ import annotations

from easy_fints.client import FinTSClient
from easy_fints.models import FinTSConfig


class DummyBankIdentifier:
    def __init__(self, bank_code: str):
        self.bank_code = bank_code


class DummySepaAccount:
    def __init__(
        self,
        *,
        iban: str,
        bic: str,
        accountnumber: str,
        subaccount: str | None,
        blz: str,
    ):
        self.iban = iban
        self.bic = bic
        self.accountnumber = accountnumber
        self.subaccount = subaccount
        self.blz = blz


class DummyLowLevelClient:
    def __init__(self):
        self._standing_dialog = object()
        self._accounts = [
            DummySepaAccount(
                iban="DE00123456780000000001",
                bic="TESTDEFFXXX",
                accountnumber="00000001",
                subaccount=None,
                blz="12345678",
            )
        ]

    def get_sepa_accounts(self):
        return self._accounts

    def get_information(self):
        return {
            "accounts": [
                {
                    "iban": "DE00123456780000000001",
                    "account_number": "00000001",
                    "subaccount_number": "42",
                    "bank_identifier": DummyBankIdentifier("12345678"),
                    "owner_name": ["Max", "Mustermann"],
                    "product_name": "Girokonto",
                    "type": "1",
                    "currency": "EUR",
                }
            ]
        }


def test_resume_accounts_enriches_owner_name_and_subaccount_from_hiupd():
    client = FinTSClient(
        FinTSConfig(
            user="demo-user",
            pin="demo-pin",
            server="https://bank.example/fints",
            product_id="demo-product",
        )
    )
    client._client = DummyLowLevelClient()

    accounts = client.resume_accounts()

    assert len(accounts) == 1
    assert accounts[0].subaccount_number == "42"
    assert accounts[0].owner_name == "Max Mustermann"
    assert accounts[0].product_name == "Girokonto"
    assert accounts[0].account_type == "Girokonto / Kontokorrentkonto"
    assert accounts[0].account_type_code == "1"
    assert accounts[0].currency == "EUR"
    assert accounts[0].label == "Girokonto (DE00123456780000000001)"
