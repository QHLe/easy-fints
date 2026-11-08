from __future__ import annotations

import datetime as dt
from decimal import Decimal

import fints.client
import mt940
import pytest
from fints.camt_parser import camt053_to_dict
from fints.models import Transaction

from easy_fints.transaction_mapping import normalize_transaction


def _mt940_statement(status, details):
    closing_balance = "987,66" if status.upper() in {"D", "RC"} else "1012,34"
    return f""":20:TEST
:25:DE37604914300587682000
:28C:1/1
:60F:C260610EUR1000,00
:61:2606100611{status}12,34NTRFNONREF
:86:{details}
:62F:C260611EUR{closing_balance}
"""


@pytest.mark.parametrize("status", ["C", "D", "RC", "RD", "c", "d", "rc", "rd"])
def test_mt940_parser_preserves_counterparty_and_sign(status):
    source = _mt940_statement(
        status,
        "166?00SEPA TRANSFER?20Invoice 123?30GENODEF1XXX?31DE09503201910039455340?32Sender GmbH",
    )

    tx = fints.client.mt940_to_array(source)[0]
    row = normalize_transaction(tx, include_debug=True)

    expected_amount = Decimal("-12.34") if status.upper() in {"D", "RC"} else Decimal("12.34")
    assert row["amount"] == expected_amount
    assert row["currency"] == "EUR"
    assert row["booking_date"] == dt.date(2026, 6, 11)
    assert row["value_date"] == dt.date(2026, 6, 10)
    assert row["counterparty_name"] == "Sender GmbH"
    assert row["counterparty_iban"] == "DE09503201910039455340"
    assert row["purpose"] == "Invoice 123"
    assert row["__debug__"]["applied_modules"] == ["default"]


def test_mt940_does_not_use_bank_code_or_recipient_as_counterparty():
    source = _mt940_statement("D", "166?00SEPA TRANSFER?20Invoice 123?30GENODEF1XXX?35Account Owner")

    row = normalize_transaction(fints.client.mt940_to_array(source)[0])

    assert row["counterparty_name"] is None
    assert row["counterparty_iban"] is None


def test_mt940_retains_unstructured_purpose():
    source = _mt940_statement("C", "Invoice 123")

    row = normalize_transaction(fints.client.mt940_to_array(source)[0])

    assert row["purpose"] == "Invoice 123"


@pytest.mark.parametrize(
    ("status", "expected_amount"),
    [("RC", "-12.34"), ("RD", "12.34"), ("d", "-12.34")],
)
def test_mt940_normalization_handles_parser_without_compatibility_options(status, expected_amount):
    tx = mt940.models.Transactions().parse(_mt940_statement(status, "Invoice 123"))[0]

    row = normalize_transaction(tx)

    assert row["amount"] == Decimal(expected_amount)


def _camt_report(indicator, wrapped_name=True):
    creditor_name = "<Nm>Recipient GmbH</Nm>"
    debtor_name = "<Nm>Sender GmbH</Nm>"
    if wrapped_name:
        creditor_name = f"<Pty>{creditor_name}</Pty>"
        debtor_name = f"<Pty>{debtor_name}</Pty>"
    version = "08" if wrapped_name else "02"
    return f"""<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.052.001.{version}">
  <BkToCstmrAcctRpt><Rpt>
    <Acct><Id><IBAN>DE37604914300587682000</IBAN></Id><Ccy>EUR</Ccy></Acct>
    <Ntry>
      <Amt Ccy="EUR">12.34</Amt><CdtDbtInd>{indicator}</CdtDbtInd>
      <BookgDt><Dt>2026-06-11</Dt></BookgDt><ValDt><Dt>2026-06-10</Dt></ValDt>
      <NtryDtls><TxDtls>
        <RltdPties>
          <Cdtr>{creditor_name}</Cdtr>
          <CdtrAcct><Id><IBAN>DE37604914300587682000</IBAN></Id></CdtrAcct>
          <Dbtr>{debtor_name}</Dbtr>
          <DbtrAcct><Id><IBAN>DE09503201910039455340</IBAN></Id></DbtrAcct>
        </RltdPties>
        <RmtInf><Ustrd>Invoice 123</Ustrd></RmtInf>
      </TxDtls></NtryDtls>
    </Ntry>
  </Rpt></BkToCstmrAcctRpt>
</Document>"""


@pytest.mark.parametrize("wrapped_name", [False, True])
@pytest.mark.parametrize(
    ("indicator", "expected_name", "expected_iban", "expected_amount"),
    [
        ("CRDT", "Sender GmbH", "DE09503201910039455340", "12.34"),
        ("DBIT", "Recipient GmbH", "DE37604914300587682000", "-12.34"),
    ],
)
def test_camt_xml_parser_preserves_counterparty_and_sign(
    wrapped_name, indicator, expected_name, expected_iban, expected_amount
):
    records = camt053_to_dict(_camt_report(indicator, wrapped_name))

    row = normalize_transaction(Transaction(data=records[0]))

    assert row["amount"] == expected_amount
    assert row["currency"] == "EUR"
    assert row["booking_date"] == "2026-06-11"
    assert row["value_date"] == "2026-06-10"
    assert row["counterparty_name"] == expected_name
    assert row["counterparty_iban"] == expected_iban
    assert row["purpose"] == "Invoice 123"


@pytest.mark.parametrize("amount", ["-12.34", Decimal("-12.34"), -12.34])
def test_camt_credit_indicator_corrects_negative_amount(amount):
    row = normalize_transaction(Transaction(data={"Amount": amount, "CreditDebitIndicator": "CRDT"}))

    assert Decimal(str(row["amount"])) == Decimal("12.34")


@pytest.mark.parametrize("reversal", ["true", "1"])
@pytest.mark.parametrize(
    ("indicator", "expected_name", "expected_iban", "expected_amount"),
    [
        ("CRDT", "Recipient GmbH", "DE37604914300587682000", "12.34"),
        ("DBIT", "Sender GmbH", "DE09503201910039455340", "-12.34"),
    ],
)
def test_camt_reversal_uses_original_parties(
    reversal, indicator, expected_name, expected_iban, expected_amount
):
    source = _camt_report(indicator).replace(
        "</CdtDbtInd>", f"</CdtDbtInd><RvslInd>{reversal}</RvslInd>"
    )
    record = camt053_to_dict(source)[0]

    row = normalize_transaction(Transaction(data=record))

    assert row["amount"] == expected_amount
    assert row["counterparty_name"] == expected_name
    assert row["counterparty_iban"] == expected_iban


def test_camt_reversal_does_not_fall_back_to_direction_derived_applicant():
    source = _camt_report("CRDT").replace("</CdtDbtInd>", "</CdtDbtInd><RvslInd>true</RvslInd>")
    record = camt053_to_dict(source)[0]
    record = {
        key: value for key, value in record.items()
        if ".Creditor." not in key and ".CreditorAccount." not in key
    }

    row = normalize_transaction(Transaction(data=record))

    assert row["counterparty_name"] is None
    assert row["counterparty_iban"] is None
