from __future__ import annotations

import datetime as dt
from decimal import Decimal
from types import SimpleNamespace

from fints.models import Amount, Transaction

from easy_fints.helpers import normalize_transaction


def test_normalize_transaction_supports_flat_camt_keys():
    tx = SimpleNamespace(
        data={
            "Amount": "12.00",
            "CreditDebitIndicator": "DBIT",
            "BookingDate.Date": "2026-04-13",
            "ValueDate.Date": "2026-04-13",
        }
    )

    row = normalize_transaction(tx, include_debug=True)

    assert row["booking_date"] == "2026-04-13"
    assert row["value_date"] == "2026-04-13"
    assert row["amount"] == "-12.00"
    assert row["__debug__"]["sources"]["booking_date"] == "vr_camt.data.BookingDate.Date"
    assert row["__debug__"]["sources"]["amount"] == "vr_camt.data.Amount"
    assert "vr_camt" in row["__debug__"]["applied_modules"]


def test_normalize_transaction_supports_nested_camt_amount_fields():
    tx = SimpleNamespace(
        data={
            "BookingDate": {"Date": "2026-04-13"},
            "ValueDate": {"Date": "2026-04-14"},
            "CreditDebitIndicator": "CRDT",
            "EntryDetails": {
                "TransactionDetails": {
                    "Amount": {"#text": "7.89", "@Ccy": "EUR"},
                    "RemittanceInformation": {"Unstructured": "Refund"},
                }
            },
        }
    )

    row = normalize_transaction(tx)

    assert row["booking_date"] == "2026-04-13"
    assert row["value_date"] == "2026-04-14"
    assert row["amount"] == "7.89"
    assert row["currency"] == "EUR"
    assert row["purpose"] == "Refund"


def test_normalize_transaction_supports_fints_namedtuple_transaction():
    tx = Transaction(
        data={
            "Amount": "12.00",
            "CreditDebitIndicator": "DBIT",
            "BookingDate.Date": "2026-04-13",
            "ValueDate.Date": "2026-04-13",
            "EntryDetails.TransactionDetails.RelatedParties.Creditor.Party.Name": "Ausgabe einer Debitkarte",
            "EntryDetails.TransactionDetails.RelatedParties.CreditorAccount.Identification.IBAN": "DE37604914300587682000",
            "EntryDetails.TransactionDetails.RemittanceInformation.Unstructured": "Jahrespreis girocard",
            "amount": Amount(amount=Decimal("-12.00"), currency="EUR"),
            "currency": "EUR",
            "date": dt.date(2026, 4, 13),
            "entry_date": dt.date(2026, 4, 13),
            "applicant_iban": "DE37604914300587682000",
            "applicant_name": "Ausgabe einer Debitkarte",
            "purpose": "Jahrespreis girocard",
        }
    )

    row = normalize_transaction(tx, include_debug=True)

    assert row["booking_date"] == "2026-04-13"
    assert row["value_date"] == "2026-04-13"
    assert row["amount"] == "-12.00"
    assert row["currency"] == "EUR"
    assert row["counterparty_name"] == "Ausgabe einer Debitkarte"
    assert row["counterparty_iban"] == "DE37604914300587682000"
    assert row["purpose"] == "Jahrespreis girocard"
    assert row["__debug__"]["raw_keys"]
    assert row["__debug__"]["sources"]["booking_date"] == "vr_camt.data.BookingDate.Date"
    assert row["__debug__"]["sources"]["amount"] == "vr_camt.data.Amount"
    assert row["__debug__"]["applied_modules"] == ["vr_camt", "default"]


def test_normalize_transaction_assigns_distinct_fints_dates():
    tx = Transaction(data={"date": dt.date(2026, 4, 11), "entry_date": dt.date(2026, 4, 13)})
    row = normalize_transaction(tx, include_debug=True)
    assert row["booking_date"] == dt.date(2026, 4, 13)
    assert row["value_date"] == dt.date(2026, 4, 11)
    assert row["__debug__"]["sources"]["booking_date"] == "default.data.entry_date"
    assert row["__debug__"]["sources"]["value_date"] == "default.data.date"


def test_normalize_transaction_prefers_camt_fields_over_generic_dates():
    tx = Transaction(data={
        "BookingDate.Date": "2026-04-13", "ValueDate.Date": "2026-04-11",
        "date": dt.date(2026, 4, 11), "entry_date": dt.date(2026, 4, 13),
    })
    row = normalize_transaction(tx, include_debug=True)
    assert row["booking_date"] == "2026-04-13"
    assert row["value_date"] == "2026-04-11"
    assert row["__debug__"]["sources"]["booking_date"] == "vr_camt.data.BookingDate.Date"


def test_normalize_transaction_uses_available_value_date_before_booking_fallback():
    tx = SimpleNamespace(booking_date="2026-04-13", data={"date": "2026-04-11"})
    row = normalize_transaction(tx)
    assert row["booking_date"] == "2026-04-13"
    assert row["value_date"] == "2026-04-11"


def test_camt_value_date_falls_back_to_generic_value_date_before_booking_date():
    tx = SimpleNamespace(data={"BookingDate.Date": "2026-04-13", "date": "2026-04-11"})
    row = normalize_transaction(tx)
    assert row["booking_date"] == "2026-04-13"
    assert row["value_date"] == "2026-04-11"
