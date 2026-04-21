from __future__ import annotations

from typing import Any

from .base import (
    MappingModuleResult,
    apply_credit_debit_indicator,
    data_value,
    first_present_with_source,
    normalize_amount,
    tx_counterparty_iban_candidate,
    tx_counterparty_name_candidate,
    tx_purpose_candidate,
)

NAME = "vr_camt"


def applies(data: dict[str, Any]) -> bool:
    return bool(
        data_value(
            data,
            "BookingDate.Date",
            "ValueDate.Date",
            "Amount",
            "EntryDetails.TransactionDetails.Amount",
            "EntryDetails.TransactionDetails.RelatedParties.Creditor.Party.Name",
            "EntryDetails.TransactionDetails.RelatedParties.CreditorAccount.Identification.IBAN",
            "CreditDebitIndicator",
        )
    )


def map_transaction(tx: Any, data: dict[str, Any]) -> MappingModuleResult:
    booking_date, booking_date_source = first_present_with_source(
        ("data.BookingDate.Date", data_value(data, "BookingDate.Date")),
    )
    value_date, value_date_source = first_present_with_source(
        ("data.ValueDate.Date", data_value(data, "ValueDate.Date")),
        ("data.BookingDate.Date", data_value(data, "BookingDate.Date")),
    )
    raw_amount_value, amount_source = first_present_with_source(
        ("data.Amount", data_value(data, "Amount")),
        (
            "data.EntryDetails.TransactionDetails.Amount",
            data_value(data, "EntryDetails.TransactionDetails.Amount"),
        ),
    )
    amount_value, amount_currency = normalize_amount(raw_amount_value)
    amount_value = apply_credit_debit_indicator(
        amount_value,
        data_value(data, "CreditDebitIndicator", "EntryDetails.TransactionDetails.CreditDebitIndicator"),
    )
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
        (
            "data.EntryDetails.TransactionDetails.RelatedParties.Creditor.Party.Name",
            data_value(data, "EntryDetails.TransactionDetails.RelatedParties.Creditor.Party.Name"),
        ),
        (
            "data.EntryDetails.TransactionDetails.RelatedParties.Debtor.Party.Name",
            data_value(data, "EntryDetails.TransactionDetails.RelatedParties.Debtor.Party.Name"),
        ),
        ("data.RelatedParties.Creditor.Party.Name", data_value(data, "RelatedParties.Creditor.Party.Name")),
        ("data.RelatedParties.Debtor.Party.Name", data_value(data, "RelatedParties.Debtor.Party.Name")),
        ("data.RelatedParties.Creditor.Name", data_value(data, "RelatedParties.Creditor.Name")),
        ("data.RelatedParties.Debtor.Name", data_value(data, "RelatedParties.Debtor.Name")),
    )
    counterparty_iban, counterparty_iban_source = tx_counterparty_iban_candidate(
        tx,
        data,
        (
            "data.EntryDetails.TransactionDetails.RelatedParties.CreditorAccount.Identification.IBAN",
            data_value(data, "EntryDetails.TransactionDetails.RelatedParties.CreditorAccount.Identification.IBAN"),
        ),
        (
            "data.EntryDetails.TransactionDetails.RelatedParties.DebtorAccount.Identification.IBAN",
            data_value(data, "EntryDetails.TransactionDetails.RelatedParties.DebtorAccount.Identification.IBAN"),
        ),
        (
            "data.RelatedParties.CreditorAccount.Identification.IBAN",
            data_value(data, "RelatedParties.CreditorAccount.Identification.IBAN"),
        ),
        (
            "data.RelatedParties.DebtorAccount.Identification.IBAN",
            data_value(data, "RelatedParties.DebtorAccount.Identification.IBAN"),
        ),
        (
            "data.EntryDetails.TransactionDetails.RelatedParties.CreditorAccount.IBAN",
            data_value(data, "EntryDetails.TransactionDetails.RelatedParties.CreditorAccount.IBAN"),
        ),
        (
            "data.EntryDetails.TransactionDetails.RelatedParties.DebtorAccount.IBAN",
            data_value(data, "EntryDetails.TransactionDetails.RelatedParties.DebtorAccount.IBAN"),
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
