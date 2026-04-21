from __future__ import annotations

import datetime as dt

from easy_fints import FinTS
from easy_fints.models import FinTSConfig


class DummyClient:
    def __init__(self, config: FinTSConfig):
        self.config = config
        self.calls: list[tuple[str, object]] = []

    def close(self) -> None:
        self.calls.append(("close", None))

    def list_accounts(self, account_filter=None):
        self.calls.append(("list_accounts", account_filter))
        return ["accounts"]

    def list_transactions(self, **kwargs):
        self.calls.append(("list_transactions", kwargs))
        return ["transactions"]

    def initiate_transfer(self, **kwargs):
        self.calls.append(("initiate_transfer", kwargs))
        return {"ok": True}

    def confirm_pending(self, tan=""):
        self.calls.append(("confirm_pending", tan))
        return (None, None, {"confirmed": True})

    def approve_vop(self):
        self.calls.append(("approve_vop", None))
        return (None, None, {"approved": True})


def test_service_builds_shared_client_with_product_id(monkeypatch):
    created: list[DummyClient] = []

    def fake_client(config: FinTSConfig):
        client = DummyClient(config)
        created.append(client)
        return client

    monkeypatch.setattr("easy_fints.library.FinTSClient", fake_client)

    service = FinTS(
        product_id="demo-product",
        bank="12345678",
        user="demo-user",
        pin="demo-pin",
        server="https://bank.example/fints",
    )

    assert service.accounts() == ["accounts"]
    assert service.transactions(days=14) == ["transactions"]
    assert service.transfer(
        source_account="DE00123456780000000000",
        account_name="Max Mustermann",
        recipient_name="Erika Musterfrau",
        recipient_iban="DE02120300000000202051",
        recipient_bic="BYLADEM1001",
        amount="12.34",
        purpose="Test",
        execution_date=dt.date(2030, 1, 1),
    ) == {"ok": True}

    client = created[0]
    assert client.config.product_id == "demo-product"
    assert client.calls[0] == ("list_accounts", None)
    assert client.calls[1] == ("list_transactions", {"account_filter": None, "days": 14, "date_from": None, "date_to": None})
    assert client.calls[2][0] == "initiate_transfer"


def test_service_close_delegates_to_shared_client(monkeypatch):
    created: list[DummyClient] = []

    def fake_client(config: FinTSConfig):
        client = DummyClient(config)
        created.append(client)
        return client

    monkeypatch.setattr("easy_fints.library.FinTSClient", fake_client)

    service = FinTS(
        product_id="demo-product",
        bank="12345678",
        user="demo-user",
        pin="demo-pin",
        server="https://bank.example/fints",
    )

    service.close()

    assert created[0].calls == [("close", None)]
