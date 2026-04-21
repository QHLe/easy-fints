from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

NORMALIZED_TRANSACTION_FIELDS = (
    "booking_date",
    "value_date",
    "amount",
    "currency",
    "counterparty_name",
    "counterparty_iban",
    "purpose",
)


def field_present(value: Any) -> bool:
    return value is not None and not (isinstance(value, str) and value == "")


def first_present(*values: Any) -> Any:
    for value in values:
        if field_present(value):
            return value
    return None


def first_present_with_source(*candidates: tuple[str, Any]) -> tuple[Any, Optional[str]]:
    for source, value in candidates:
        if field_present(value):
            return (value, source)
    return (None, None)


def transaction_data(tx: Any) -> dict[str, Any]:
    data = getattr(tx, "data", None)
    if isinstance(data, dict):
        return data
    data = getattr(tx, "__dict__", {}).get("data")
    return data if isinstance(data, dict) else {}


def data_value(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in data:
            value = data[key]
        else:
            value: Any = data
            for part in key.split("."):
                if not isinstance(value, dict) or part not in value:
                    value = None
                    break
                value = value[part]
        if field_present(value):
            return value
    return None


def json_compatible(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_compatible(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_compatible(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    return str(value)


def normalize_amount(value: Any) -> tuple[Any, Any]:
    if value is None:
        return (None, None)
    if isinstance(value, dict):
        amount = first_present(
            value.get("amount"),
            value.get("Amount"),
            value.get("value"),
            value.get("#text"),
        )
        currency = first_present(
            value.get("currency"),
            value.get("Currency"),
            value.get("Ccy"),
            value.get("@Ccy"),
        )
        if amount is not None:
            return (amount, currency)
    amount = getattr(value, "amount", None)
    currency = getattr(value, "currency", None)
    if amount is not None:
        return (amount, currency)
    if isinstance(value, (tuple, list)) and value:
        amount = value[0]
        currency = value[1] if len(value) > 1 else None
        return (amount, currency)
    return (value, None)


def apply_credit_debit_indicator(amount: Any, indicator: Any) -> Any:
    if amount is None:
        return None
    normalized_indicator = str(indicator).strip().upper() if indicator is not None else ""
    if normalized_indicator != "DBIT":
        return amount
    if isinstance(amount, str):
        stripped = amount.strip()
        if not stripped or stripped.startswith("-"):
            return stripped or amount
        if stripped.startswith("+"):
            return f"-{stripped[1:]}"
        return f"-{stripped}"
    if isinstance(amount, Decimal):
        return amount if amount <= 0 else -amount
    if isinstance(amount, (int, float)):
        return amount if amount <= 0 else -amount
    try:
        decimal_amount = Decimal(str(amount))
    except (InvalidOperation, TypeError, ValueError):
        return amount
    if decimal_amount <= 0:
        return amount
    amount_text = str(amount).strip()
    if amount_text.startswith("+"):
        amount_text = amount_text[1:]
    return f"-{amount_text}"


def empty_transaction_row(tx: Any) -> dict[str, Any]:
    return {
        "booking_date": None,
        "value_date": None,
        "amount": None,
        "currency": None,
        "counterparty_name": None,
        "counterparty_iban": None,
        "purpose": None,
        "raw": repr(tx),
    }


def transaction_debug_failure_reasons(row: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if row.get("booking_date") is None and row.get("value_date") is None:
        reasons.append("missing_dates")
    if row.get("amount") is None:
        reasons.append("missing_amount")
    return reasons


def module_applied(values: dict[str, Any]) -> bool:
    return any(field_present(values.get(field)) for field in NORMALIZED_TRANSACTION_FIELDS)


@dataclass(slots=True)
class MappingModuleResult:
    values: dict[str, Any]
    sources: dict[str, Optional[str]]


def tx_date_candidate(data: dict[str, Any], *extra: tuple[str, Any]) -> tuple[Any, Optional[str]]:
    return first_present_with_source(
        *extra,
        ("data.date", data_value(data, "date")),
        ("data.entry_date", data_value(data, "entry_date")),
    )


def tx_value_date_candidate(data: dict[str, Any], *extra: tuple[str, Any]) -> tuple[Any, Optional[str]]:
    return first_present_with_source(
        *extra,
        ("data.entry_date", data_value(data, "entry_date")),
        ("data.date", data_value(data, "date")),
    )


def tx_amount_candidate(tx: Any, data: dict[str, Any], *extra: tuple[str, Any]) -> tuple[Any, Optional[str]]:
    return first_present_with_source(
        ("tx.amount", getattr(tx, "amount", None)),
        ("tx.transaction_amount", getattr(tx, "transaction_amount", None)),
        ("tx.value", getattr(tx, "value", None)),
        *extra,
        ("data.amount", data_value(data, "amount")),
    )


def tx_currency_candidate(tx: Any, amount_currency: Any, data: dict[str, Any], *extra: tuple[str, Any]) -> tuple[Any, Optional[str]]:
    return first_present_with_source(
        ("tx.currency", getattr(tx, "currency", None)),
        ("normalized_amount.currency", amount_currency),
        *extra,
        ("data.currency", data_value(data, "currency")),
    )


def tx_counterparty_name_candidate(tx: Any, data: dict[str, Any], *extra: tuple[str, Any]) -> tuple[Any, Optional[str]]:
    return first_present_with_source(
        ("tx.counterparty_name", getattr(tx, "counterparty_name", None)),
        ("tx.name", getattr(tx, "name", None)),
        ("tx.other_account_name", getattr(tx, "other_account_name", None)),
        ("tx.recipient_name", getattr(tx, "recipient_name", None)),
        *extra,
        ("data.applicant_name", data_value(data, "applicant_name")),
        ("data.recipient_name", data_value(data, "recipient_name")),
    )


def tx_counterparty_iban_candidate(tx: Any, data: dict[str, Any], *extra: tuple[str, Any]) -> tuple[Any, Optional[str]]:
    return first_present_with_source(
        ("tx.counterparty_iban", getattr(tx, "counterparty_iban", None)),
        ("tx.iban", getattr(tx, "iban", None)),
        ("tx.account", getattr(tx, "account", None)),
        ("tx.other_account", getattr(tx, "other_account", None)),
        *extra,
        ("data.applicant_iban", data_value(data, "applicant_iban")),
        ("data.recipient_iban", data_value(data, "recipient_iban")),
        ("data.applicant_bin", data_value(data, "applicant_bin")),
    )


def tx_purpose_candidate(tx: Any, data: dict[str, Any], *extra: tuple[str, Any]) -> tuple[Any, Optional[str]]:
    return first_present_with_source(
        ("tx.usage", getattr(tx, "usage", None)),
        ("tx.purpose", getattr(tx, "purpose", None)),
        ("tx.text", getattr(tx, "text", None)),
        ("tx.remittance_information", getattr(tx, "remittance_information", None)),
        *extra,
        ("data.purpose", data_value(data, "purpose")),
        ("data.additional_purpose", data_value(data, "additional_purpose")),
        ("data.posting_text", data_value(data, "posting_text")),
    )
