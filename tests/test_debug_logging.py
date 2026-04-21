from __future__ import annotations

import datetime as dt
import json
from types import SimpleNamespace

from easy_fints.client import FinTSClient
from easy_fints.models import FinTSConfig


def _make_client() -> FinTSClient:
    return FinTSClient(
        FinTSConfig(
            user="demo-user",
            pin="super-secret-pin",
            server="https://bank.example.test/fints",
            product_id="PYFIN",
        )
    )


def test_transaction_debug_fail_only_skips_successful_records(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FINTS_DEBUG_LEVEL", "record_raw")
    monkeypatch.setenv("FINTS_DEBUG_FAIL_ONLY", "1")

    client = _make_client()
    account = SimpleNamespace(iban="DE00123456780000000001")
    rows = client._normalize_transaction_rows(
        [
            SimpleNamespace(
                data={
                    "Amount": "12.00",
                    "CreditDebitIndicator": "DBIT",
                    "BookingDate.Date": "2026-04-13",
                    "ValueDate.Date": "2026-04-13",
                }
            )
        ],
        account=account,
        start_date=dt.date(2026, 4, 1),
        end_date=dt.date(2026, 4, 21),
    )

    assert rows[0]["booking_date"] == "2026-04-13"
    assert rows[0]["amount"] == "-12.00"
    assert not (tmp_path / "logs" / "debug.log").exists()


def test_transaction_debug_fail_only_logs_failed_records(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FINTS_DEBUG_LEVEL", "record_raw")
    monkeypatch.setenv("FINTS_DEBUG_FAIL_ONLY", "1")

    client = _make_client()
    account = SimpleNamespace(iban="DE00123456780000000001")
    client._normalize_transaction_rows(
        [
            SimpleNamespace(
                data={
                    "Amount": "12.00",
                    "CreditDebitIndicator": "DBIT",
                }
            )
        ],
        account=account,
        start_date=dt.date(2026, 4, 1),
        end_date=dt.date(2026, 4, 21),
    )

    records = [
        json.loads(line)
        for line in (tmp_path / "logs" / "debug.log").read_text(encoding="utf-8").splitlines()
    ]

    assert [record["stage"] for record in records] == ["summary", "mapping", "record_raw"]
    assert records[0]["failed_record_count"] == 1
    assert records[1]["failure_reasons"] == ["missing_dates"]
    assert records[1]["selected_sources"]["amount"] == "vr_camt.data.Amount"
    assert records[1]["mapping_modules"] == ["vr_camt"]
    assert records[2]["raw_data"]["Amount"] == "12.00"
