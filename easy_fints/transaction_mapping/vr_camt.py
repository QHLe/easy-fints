from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from .base import (
    MappingModuleResult,
    apply_credit_debit_indicator,
    data_value,
    first_present_with_source,
    is_camt_reversal,
    normalize_amount,
    tx_amount_candidate,
    tx_counterparty_iban_candidate,
    tx_counterparty_name_candidate,
    tx_purpose_candidate,
)

NAME = "vr_camt"


def applies(data: dict[str, Any]) -> bool:
    camt_fields = ("BookingDate", "ValueDate", "Amount", "EntryDetails", "RelatedParties", "CreditDebitIndicator")
    return any(key.split(".", 1)[0] in camt_fields for key in data)


def map_transaction(tx: Any, data: dict[str, Any]) -> MappingModuleResult:
    booking_date, booking_date_source = first_present_with_source(
        ("data.BookingDate.Date", data_value(data, "BookingDate.Date")),
    )
    value_date, value_date_source = first_present_with_source(
        ("data.ValueDate.Date", data_value(data, "ValueDate.Date")),
    )
    raw_amount_value, amount_source = first_present_with_source(
        ("data.Amount", data_value(data, "Amount")),
        (
            "data.EntryDetails.TransactionDetails.Amount",
            data_value(data, "EntryDetails.TransactionDetails.Amount"),
        ),
    )
    if raw_amount_value is None:
        raw_amount_value, amount_source = tx_amount_candidate(tx, data)
    amount_value, amount_currency = normalize_amount(raw_amount_value)
    indicator = str(
        data_value(data, "CreditDebitIndicator", "EntryDetails.TransactionDetails.CreditDebitIndicator") or ""
    ).strip().upper()
    amount_value = apply_credit_debit_indicator(amount_value, indicator)
    is_credit = indicator == "CRDT"
    if not indicator and amount_value is not None:
        try:
            is_credit = Decimal(str(amount_value)) > 0
        except (InvalidOperation, TypeError, ValueError):
            pass
    # Reversals retain the original parties while the entry's money flow reverses.
    if is_camt_reversal(data):
        is_credit = not is_credit
    party = "Debtor" if is_credit else "Creditor"
    currency, currency_source = first_present_with_source(
        ("data.Currency", data_value(data, "Currency")),
        ("data.Amount.Ccy", data_value(data, "Amount.Ccy")),
        ("data.Amount.@Ccy", data_value(data, "Amount.@Ccy")),
        ("data.Amount.Currency", data_value(data, "Amount.Currency")),
        (
            "data.EntryDetails.TransactionDetails.Amount.Ccy",
            data_value(data, "EntryDetails.TransactionDetails.Amount.Ccy"),
        ),
        (
            "data.EntryDetails.TransactionDetails.Amount.@Ccy",
            data_value(data, "EntryDetails.TransactionDetails.Amount.@Ccy"),
        ),
        (
            "data.EntryDetails.TransactionDetails.Amount.Currency",
            data_value(data, "EntryDetails.TransactionDetails.Amount.Currency"),
        ),
        ("normalized_amount.currency", amount_currency),
    )
    counterparty_name, counterparty_name_source = tx_counterparty_name_candidate(
        tx,
        data,
        *(
            (f"data.{path}", data_value(data, path))
            for path in (
                f"EntryDetails.TransactionDetails.RelatedParties.{party}.Party.Name",
                f"EntryDetails.TransactionDetails.RelatedParties.{party}.Name",
                f"RelatedParties.{party}.Party.Name",
                f"RelatedParties.{party}.Name",
            )
        ),
    )
    counterparty_iban, counterparty_iban_source = tx_counterparty_iban_candidate(
        tx,
        data,
        *(
            (f"data.{path}", data_value(data, path))
            for path in (
                f"EntryDetails.TransactionDetails.RelatedParties.{party}Account.Identification.IBAN",
                f"RelatedParties.{party}Account.Identification.IBAN",
                f"EntryDetails.TransactionDetails.RelatedParties.{party}Account.IBAN",
                f"RelatedParties.{party}Account.IBAN",
            )
        ),
    )
    purpose, purpose_source = tx_purpose_candidate(
        tx,
        data,
        (
            "data.EntryDetails.TransactionDetails.RemittanceInformation.Unstructured",
            data_value(data, "EntryDetails.TransactionDetails.RemittanceInformation.Unstructured"),
        ),
        (
            "data.RemittanceInformation.Unstructured",
            data_value(data, "RemittanceInformation.Unstructured"),
        ),
        (
            "data.AdditionalEntryInformation",
            data_value(data, "AdditionalEntryInformation"),
        ),
        (
            "data.AdditionalTransactionInfo",
            data_value(data, "AdditionalTransactionInfo"),
        ),
    )
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
