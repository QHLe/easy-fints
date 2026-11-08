from __future__ import annotations

from decimal import Decimal

import pytest
from fints.models import Transaction

from easy_fints.transaction_mapping import normalize_transaction


@pytest.fixture()
def camt_data():
    return {
        "CreditDebitIndicator": "CRDT",
        "Amount": "806.30",
        "BookingDate": {"Date": "2026-06-10"},
        "EntryDetails": {
            "TransactionDetails": {
                "RelatedParties": {
                    "Creditor": {"Party": {"Name": "Recipient GmbH"}},
                    "CreditorAccount": {"Identification": {"IBAN": "DE37604914300587682000"}},
                    "Debtor": {"Party": {"Name": "Sender GmbH"}},
                    "DebtorAccount": {"Identification": {"IBAN": "DE09503201910039455340"}},
                }
            }
        },
    }


@pytest.mark.parametrize("nested_indicator", [False, True])
@pytest.mark.parametrize(
    ("indicator", "amount", "expected_name", "expected_iban"),
    [
        ("CRDT", "806.30", "Sender GmbH", "DE09503201910039455340"),
        (" crdt ", "-806.30", "Sender GmbH", "DE09503201910039455340"),
        ("CRDT", None, "Sender GmbH", "DE09503201910039455340"),
        ("CRDT", "invalid", "Sender GmbH", "DE09503201910039455340"),
        ("DBIT", "806.30", "Recipient GmbH", "DE37604914300587682000"),
        (" dbit ", "-806.30", "Recipient GmbH", "DE37604914300587682000"),
        (None, "806.30", "Sender GmbH", "DE09503201910039455340"),
        (" ", Decimal("1E-1000"), "Sender GmbH", "DE09503201910039455340"),
        (None, "-806.30", "Recipient GmbH", "DE37604914300587682000"),
        (None, "0", "Recipient GmbH", "DE37604914300587682000"),
        (None, None, "Recipient GmbH", "DE37604914300587682000"),
        (None, "invalid", "Recipient GmbH", "DE37604914300587682000"),
        (None, "NaN", "Recipient GmbH", "DE37604914300587682000"),
        ("UNKNOWN", "806.30", "Recipient GmbH", "DE37604914300587682000"),
    ],
)
def test_camt_counterparty_follows_direction(
    camt_data, nested_indicator, indicator, amount, expected_name, expected_iban
):
    camt_data.pop("CreditDebitIndicator")
    if indicator is not None:
        if nested_indicator:
            camt_data["EntryDetails"]["TransactionDetails"]["CreditDebitIndicator"] = indicator
        else:
            camt_data["CreditDebitIndicator"] = indicator
    camt_data["Amount"] = amount

    row = normalize_transaction(Transaction(data=camt_data), include_debug=True)

    assert row["counterparty_name"] == expected_name
    assert row["counterparty_iban"] == expected_iban
    party = "Debtor" if expected_name == "Sender GmbH" else "Creditor"
    source_prefix = f"vr_camt.data.EntryDetails.TransactionDetails.RelatedParties.{party}"
    assert row["__debug__"]["sources"]["counterparty_name"] == f"{source_prefix}.Party.Name"
    assert row["__debug__"]["sources"]["counterparty_iban"] == f"{source_prefix}Account.Identification.IBAN"


@pytest.mark.parametrize(
    ("indicator", "party", "other_party"),
    [("CRDT", "Debtor", "Creditor"), ("DBIT", "Creditor", "Debtor")],
)
@pytest.mark.parametrize(
    ("name_path", "iban_path"),
    [
        (
            "EntryDetails.TransactionDetails.RelatedParties.{party}.Party.Name",
            "EntryDetails.TransactionDetails.RelatedParties.{party}Account.Identification.IBAN",
        ),
        ("RelatedParties.{party}.Party.Name", "RelatedParties.{party}Account.Identification.IBAN"),
        ("RelatedParties.{party}.Name", "EntryDetails.TransactionDetails.RelatedParties.{party}Account.IBAN"),
    ],
)
def test_camt_counterparty_prefers_matching_role_across_flat_paths(
    indicator, party, other_party, name_path, iban_path
):
    name_path = name_path.format(party=party)
    iban_path = iban_path.format(party=party)
    data = {
        "CreditDebitIndicator": indicator,
        name_path: "Counterparty GmbH",
        iban_path: "DE09503201910039455340",
        f"EntryDetails.TransactionDetails.RelatedParties.{other_party}.Party.Name": "Account Owner",
        f"EntryDetails.TransactionDetails.RelatedParties.{other_party}Account.Identification.IBAN": "DE37604914300587682000",
    }

    row = normalize_transaction(Transaction(data=data), include_debug=True)

    assert row["counterparty_name"] == "Counterparty GmbH"
    assert row["counterparty_iban"] == "DE09503201910039455340"
    assert row["__debug__"]["sources"]["counterparty_name"] == f"vr_camt.data.{name_path}"
    assert row["__debug__"]["sources"]["counterparty_iban"] == f"vr_camt.data.{iban_path}"


@pytest.mark.parametrize(
    ("indicator", "party"),
    [("CRDT", "Debtor"), ("DBIT", "Creditor")],
)
@pytest.mark.parametrize("has_generic_counterparty", [False, True])
def test_camt_counterparty_falls_back_when_matching_role_is_absent(
    camt_data, indicator, party, has_generic_counterparty
):
    camt_data["CreditDebitIndicator"] = indicator
    parties = camt_data["EntryDetails"]["TransactionDetails"]["RelatedParties"]
    del parties[party]
    del parties[f"{party}Account"]
    if has_generic_counterparty:
        camt_data.update(
            applicant_name="Applicant GmbH",
            applicant_iban="DE09503201910039455340",
            recipient_name="Account Owner",
            recipient_iban="DE37604914300587682000",
        )
        expected_name = camt_data["applicant_name"]
        expected_iban = camt_data["applicant_iban"]
        name_source = "vr_camt.data.applicant_name"
        iban_source = "vr_camt.data.applicant_iban"
    else:
        expected_name = expected_iban = name_source = iban_source = None

    row = normalize_transaction(Transaction(data=camt_data), include_debug=True)

    assert row["counterparty_name"] == expected_name
    assert row["counterparty_iban"] == expected_iban
    assert row["__debug__"]["sources"]["counterparty_name"] == name_source
    assert row["__debug__"]["sources"]["counterparty_iban"] == iban_source


def test_camt_direction_uses_generic_normalized_amount_when_camt_amount_is_absent(camt_data):
    camt_data.pop("CreditDebitIndicator")
    camt_data.pop("Amount")
    camt_data["amount"] = {"amount": Decimal("806.30"), "currency": "EUR"}

    row = normalize_transaction(Transaction(data=camt_data))

    assert row["amount"] == Decimal("806.30")
    assert row["counterparty_name"] == "Sender GmbH"
    assert row["counterparty_iban"] == "DE09503201910039455340"


def test_camt_detection_handles_zero_amount(camt_data):
    camt_data.pop("BookingDate")
    camt_data["Amount"] = Decimal("0")

    row = normalize_transaction(Transaction(data=camt_data))

    assert row["amount"] == Decimal("0")
    assert row["counterparty_name"] == "Sender GmbH"


def test_camt_detection_handles_nested_indicator_without_dates_or_amount():
    data = {
        "EntryDetails": {"TransactionDetails": {"CreditDebitIndicator": "CRDT"}},
        "RelatedParties": {"Debtor": {"Name": "Sender GmbH"}},
    }

    row = normalize_transaction(Transaction(data=data))

    assert row["counterparty_name"] == "Sender GmbH"
