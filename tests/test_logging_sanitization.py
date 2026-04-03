from __future__ import annotations

import json

from src.helpers import append_operation_step_log
from src.models import FinTSConfig


def test_append_operation_step_log_sanitizes_sensitive_fields(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    log_path = append_operation_step_log(
        "transfer",
        "started",
        {
            "source_account": "DE11111111111111111111",
            "recipient_iban": "DE44670800500660521700",
            "recipient_name": "Alice Example",
            "endtoend_id": "INV-2026-0001",
            "close_match_name": "Alice Example",
            "other_identification": "Customer 123",
            "pin": "super-secret-pin",
            "tan": "123456",
            "image_base64": "ZmFrZQ==",
            "transfer_overview": {
                "source_account_label": "DE11111111111111111111",
                "recipient_iban": "DE44670800500660521700",
                "recipient_name": "Alice Example",
                "endtoend_id": "INV-2026-0001",
            },
        },
    )

    record = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])

    assert record["pin"] == "[redacted]"
    assert record["tan"] == "[redacted]"
    assert record["image_base64"] == "[redacted]"
    assert record["recipient_name"] == "[masked]"
    assert record["close_match_name"] == "[masked]"
    assert record["other_identification"] == "[masked]"
    assert record["source_account"].startswith("DE11")
    assert record["source_account"].endswith("1111")
    assert "*" in record["source_account"]
    assert record["recipient_iban"].startswith("DE44")
    assert record["recipient_iban"].endswith("1700")
    assert "*" in record["recipient_iban"]
    assert record["endtoend_id"] != "INV-2026-0001"
    assert record["transfer_overview"]["recipient_name"] == "[masked]"
    assert record["transfer_overview"]["recipient_iban"].startswith("DE44")


def test_fints_config_to_safe_dict_masks_user_and_pin():
    cfg = FinTSConfig(
        user="6686741",
        pin="super-secret-pin",
        server="https://bank.example.test/fints",
        product_id="PYFIN",
    )

    safe = cfg.to_safe_dict()

    assert safe["pin"] == "***"
    assert safe["user"] == "66***41"
