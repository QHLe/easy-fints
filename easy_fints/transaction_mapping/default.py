from __future__ import annotations

from typing import Any

from .base import (
    MappingModuleResult,
    apply_credit_debit_indicator,
    data_value,
    normalize_amount,
    tx_amount_candidate,
    tx_counterparty_iban_candidate,
    tx_counterparty_name_candidate,
    tx_currency_candidate,
    tx_date_candidate,
    tx_purpose_candidate,
    tx_value_date_candidate,
)

NAME = "default"


def applies(data: dict[str, Any]) -> bool:
    return True


def map_transaction(tx: Any, data: dict[str, Any]) -> MappingModuleResult:
    booking_date, booking_date_source = tx_date_candidate(
        data,
        ("tx.booking_date", getattr(tx, "booking_date", None)),
        ("tx.date", getattr(tx, "date", None)),
    )
    value_date, value_date_source = tx_value_date_candidate(
        data,
        ("tx.value_date", getattr(tx, "value_date", None)),
        ("tx.booking_date", getattr(tx, "booking_date", None)),
        ("tx.date", getattr(tx, "date", None)),
    )
    raw_amount_value, amount_source = tx_amount_candidate(tx, data)
    amount_value, amount_currency = normalize_amount(raw_amount_value)
    amount_value = apply_credit_debit_indicator(
        amount_value,
        data_value(data, "CreditDebitIndicator", "EntryDetails.TransactionDetails.CreditDebitIndicator"),
    )
    currency, currency_source = tx_currency_candidate(tx, amount_currency, data)
    counterparty_name, counterparty_name_source = tx_counterparty_name_candidate(tx, data)
    counterparty_iban, counterparty_iban_source = tx_counterparty_iban_candidate(tx, data)
    purpose, purpose_source = tx_purpose_candidate(tx, data)
    return MappingModuleResult(
        values={
            "booking_date": booking_date,
            "value_date": value_date,
            "amount": amount_value,
            "currency": currency,
            "counterparty_name": counterparty_name,
            "counterparty_iban": counterparty_iban,
            "purpose": purpose,
        },
        sources={
            "booking_date": booking_date_source,
            "value_date": value_date_source,
            "amount": amount_source,
            "currency": currency_source,
            "counterparty_name": counterparty_name_source,
            "counterparty_iban": counterparty_iban_source,
            "purpose": purpose_source,
        },
    )
