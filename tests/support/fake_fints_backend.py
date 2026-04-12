from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from types import SimpleNamespace

from fastapi.responses import JSONResponse

from easy_fints.exceptions import FinTSCapabilityError, TanRequiredError, VOPRequiredError
from easy_fints.models import (
    AccountSummary,
    AccountTransactions,
    TanChallenge,
    TransactionRecord,
    TransferResponse,
    VOPChallenge,
)


@dataclass
class FakeBankResponse:
    code: str
    text: str
    reference: str | None = None


@dataclass
class FakeTransactionResult:
    status: SimpleNamespace
    responses: list[FakeBankResponse]


class FakeFinTSClient:
    def __init__(self, scenario: str = "transfer_success"):
        self.scenario = scenario
        self.closed = False
        self._standing_dialog = object()
        self._pending_tan_response = None
        self._pending_vop_response = None
        self._accounts_confirmed = False
        self._transactions_stage = "new"
        self._transfer_stage = "new"
        self._latest_transfer_params: dict[str, object] = {}
        self._created_transfer_overview: dict[str, object] | None = None

    @classmethod
    def from_env(cls, env_path=None, overrides=None):
        scenario = (overrides or {}).get("scenario", "transfer_success")
        client = cls(scenario=scenario)
        CREATED_CLIENTS.append(client)
        return client

    def close(self) -> None:
        self.closed = True
        self._standing_dialog = None
        self._pending_tan_response = None
        self._pending_vop_response = None

    def clear_pending_confirmations(self) -> None:
        self._pending_tan_response = None
        self._pending_vop_response = None
        if self.scenario == "transfer_vop_retry" and self._transfer_stage == "awaiting_vop":
            self._transfer_stage = "retry_requested"

    def _has_standing_dialog(self) -> bool:
        return self._standing_dialog is not None

    def begin_accounts(self):
        if self.scenario == "accounts_tan" and not self._accounts_confirmed:
            self._pending_tan_response = object()
            raise TanRequiredError(
                "accounts",
                TanChallenge(
                    message="Enter TAN",
                    decoupled=False,
                    has_html=False,
                    has_raw=False,
                    has_matrix=False,
                    has_hhduc=False,
                ),
            )
        return [
            AccountSummary(
                label="Primary account",
                iban="DE00123456780000000001",
                bic="TESTDEFFXXX",
                bank_code="12345678",
                account_number="00000001",
                subaccount_number=None,
                bank_identifier="12345678",
            )
        ]

    def get_account_overview(self, account_filter=None, include_transaction_count_days=None):
        return self.begin_accounts()

    def list_transactions_by_account(self, account_filter=None, days=30, date_from=None, date_to=None):
        if self.scenario == "transactions_decoupled":
            if self._transactions_stage == "new":
                self._transactions_stage = "awaiting_confirm_1"
                self._pending_tan_response = object()
                raise TanRequiredError(
                    "transactions",
                    TanChallenge(
                        message="Approve in app",
                        decoupled=True,
                        has_html=False,
                        has_raw=False,
                        has_matrix=False,
                        has_hhduc=False,
                    ),
                )
            if self._transactions_stage in {"awaiting_confirm_1", "awaiting_confirm_2"}:
                raise AssertionError("transactions resumed before confirm flow completed")

        account = AccountSummary(
            label="Primary account",
            iban="DE00123456780000000001",
            bic="TESTDEFFXXX",
            bank_code="12345678",
            account_number="00000001",
            subaccount_number=None,
            bank_identifier="12345678",
        )
        return [
            AccountTransactions(
                account=account,
                transactions=[
                    TransactionRecord(
                        account_label=account.label,
                        tx_index=0,
                        booking_date="2026-04-01",
                        value_date="2026-04-01",
                        amount="-12.34",
                        currency="EUR",
                        counterparty_name="Test Merchant",
                        counterparty_iban="DE00999999990000000001",
                        purpose="Coffee",
                        raw="simulated",
                    )
                ],
            )
        ]

    def initiate_transfer(
        self,
        *,
        source_account,
        account_name,
        recipient_name,
        recipient_iban,
        recipient_bic,
        amount,
        purpose,
        endtoend_id,
        instant_payment,
        execution_date,
    ):
        self._latest_transfer_params = {
            "source_account": source_account,
            "account_name": account_name,
            "recipient_name": recipient_name,
            "recipient_iban": recipient_iban,
            "recipient_bic": recipient_bic,
            "amount": amount,
            "purpose": purpose,
            "endtoend_id": endtoend_id,
            "instant_payment": bool(instant_payment),
            "execution_date": execution_date.isoformat() if hasattr(execution_date, "isoformat") else execution_date,
        }
        self._created_transfer_overview = self._make_transfer_overview()

        if self.scenario == "transfer_instant_unsupported":
            raise FinTSCapabilityError(
                "transfer",
                "instant_payment",
                "Instant payments are not supported by this bank",
                instant_payment=True,
            )
        if self.scenario == "transfer_scheduled_unsupported":
            raise FinTSCapabilityError(
                "transfer",
                "scheduled_transfer",
                "Scheduled transfers are not supported by this bank",
                execution_date=str(self._latest_transfer_params["execution_date"]),
                instant_payment=False,
            )
        if self.scenario == "transfer_success":
            return self._transfer_response(
                status="SUCCESS",
                responses=[FakeBankResponse(code="0010", text="Order accepted.")],
            )
        if self.scenario == "transfer_vop_approve":
            if self._transfer_stage == "new":
                self._transfer_stage = "awaiting_initial_confirm"
                self._pending_tan_response = object()
                exc = TanRequiredError(
                    "transfer",
                    TanChallenge(
                        message="Approve in banking app",
                        decoupled=True,
                        has_html=False,
                        has_raw=False,
                        has_matrix=False,
                        has_hhduc=False,
                    ),
                )
                setattr(exc, "transfer_overview", self._created_transfer_overview)
                raise exc
            raise AssertionError(f"unexpected transfer stage for {self.scenario}: {self._transfer_stage}")
        if self.scenario == "transfer_vop_retry":
            if self._transfer_stage == "new":
                self._transfer_stage = "awaiting_initial_confirm"
                self._pending_tan_response = object()
                exc = TanRequiredError(
                    "transfer",
                    TanChallenge(
                        message="Approve in banking app",
                        decoupled=True,
                        has_html=False,
                        has_raw=False,
                        has_matrix=False,
                        has_hhduc=False,
                    ),
                )
                setattr(exc, "transfer_overview", self._created_transfer_overview)
                raise exc
            if self._transfer_stage == "retry_requested":
                self._transfer_stage = "awaiting_retry_confirm"
                self._pending_tan_response = object()
                exc = TanRequiredError(
                    "transfer",
                    TanChallenge(
                        message="Approve corrected transfer",
                        decoupled=True,
                        has_html=False,
                        has_raw=False,
                        has_matrix=False,
                        has_hhduc=False,
                    ),
                )
                setattr(exc, "transfer_overview", self._created_transfer_overview)
                raise exc
            raise AssertionError(f"unexpected transfer stage for {self.scenario}: {self._transfer_stage}")
        raise AssertionError(f"unsupported scenario {self.scenario}")

    def confirm_pending(self, tan: str = ""):
        if self.scenario == "accounts_tan":
            if self._pending_tan_response is None:
                raise AssertionError("missing pending account TAN")
            self._pending_tan_response = None
            self._accounts_confirmed = True
            return (None, None, None)

        if self.scenario == "transactions_decoupled":
            if self._transactions_stage == "awaiting_confirm_1":
                self._transactions_stage = "awaiting_confirm_2"
                self._pending_tan_response = object()
                return (
                    TanChallenge(
                        message="Still waiting for app confirmation",
                        decoupled=True,
                        has_html=False,
                        has_raw=False,
                        has_matrix=False,
                        has_hhduc=False,
                    ),
                    None,
                    None,
                )
            if self._transactions_stage == "awaiting_confirm_2":
                self._transactions_stage = "confirmed"
                self._pending_tan_response = None
                return (None, None, None)

        if self.scenario == "transfer_vop_approve":
            if self._transfer_stage == "awaiting_initial_confirm":
                self._transfer_stage = "awaiting_vop"
                self._pending_tan_response = None
                self._pending_vop_response = object()
                return (
                    None,
                    VOPChallenge(
                        result="RCVC",
                        message="Bank requires explicit approval of the payee verification result before execution.",
                        close_match_name=None,
                        other_identification=None,
                        na_reason=None,
                        raw_repr="simulated",
                    ),
                    None,
                )
            if self._transfer_stage == "awaiting_final_confirm":
                self._transfer_stage = "completed"
                self._pending_tan_response = None
                return (None, None, self._fake_transaction_result())

        if self.scenario == "transfer_vop_retry":
            if self._transfer_stage == "awaiting_initial_confirm":
                self._transfer_stage = "awaiting_vop"
                self._pending_tan_response = None
                self._pending_vop_response = object()
                return (
                    None,
                    VOPChallenge(
                        result="RVMC",
                        message="Recipient name partially matches: Corrected Recipient.",
                        close_match_name="Corrected Recipient",
                        other_identification=None,
                        na_reason=None,
                        raw_repr="simulated",
                    ),
                    None,
                )
            if self._transfer_stage == "awaiting_retry_confirm":
                self._transfer_stage = "completed"
                self._pending_tan_response = None
                return (None, None, self._fake_transaction_result())

        raise AssertionError(f"unexpected confirm_pending for scenario={self.scenario} stage={self._transfer_stage}")

    def approve_vop(self):
        if self.scenario == "transfer_vop_approve" and self._transfer_stage == "awaiting_vop":
            self._transfer_stage = "awaiting_final_confirm"
            self._pending_vop_response = None
            self._pending_tan_response = object()
            return (
                TanChallenge(
                    message="Approve final execution in banking app",
                    decoupled=True,
                    has_html=False,
                    has_raw=False,
                    has_matrix=False,
                    has_hhduc=False,
                ),
                None,
                None,
            )
        raise AssertionError(f"unexpected approve_vop for scenario={self.scenario} stage={self._transfer_stage}")

    def transfer_response_from_result(self, result, params, transfer_overview=None):
        amount = Decimal(str(params["amount"]))
        return TransferResponse.from_fints_response(
            response=result,
            amount=amount,
            source_account_label=self._source_account_label(),
            recipient_name=str(params["recipient_name"]),
            recipient_iban=str(params["recipient_iban"]),
            recipient_bic=params.get("recipient_bic"),
            purpose=str(params["purpose"]),
            endtoend_id=str(params.get("endtoend_id") or "NOTPROVIDED"),
            transfer_overview=transfer_overview,
        )

    def _make_transfer_overview(self) -> dict[str, object]:
        return {
            "source_account_label": self._source_account_label(),
            "recipient_name": str(self._latest_transfer_params["recipient_name"]),
            "recipient_iban": str(self._latest_transfer_params["recipient_iban"]),
            "recipient_bic": self._latest_transfer_params["recipient_bic"],
            "amount": f"{Decimal(str(self._latest_transfer_params['amount'])):.2f}",
            "currency": "EUR",
            "purpose": str(self._latest_transfer_params["purpose"]),
            "endtoend_id": str(self._latest_transfer_params["endtoend_id"] or "NOTPROVIDED"),
            "instant_payment": bool(self._latest_transfer_params["instant_payment"]),
            "execution_date": self._latest_transfer_params["execution_date"],
        }

    def _source_account_label(self) -> str:
        return str(self._latest_transfer_params.get("source_account") or "DE11111111111111111111")

    def _fake_transaction_result(self) -> FakeTransactionResult:
        return FakeTransactionResult(
            status=SimpleNamespace(name="SUCCESS"),
            responses=[FakeBankResponse(code="0010", text="Order accepted.")],
        )

    def _transfer_response(self, *, status: str, responses: list[FakeBankResponse]) -> TransferResponse:
        result = FakeTransactionResult(status=SimpleNamespace(name=status), responses=responses)
        return TransferResponse.from_fints_response(
            response=result,
            amount=Decimal(str(self._latest_transfer_params["amount"])),
            source_account_label=self._source_account_label(),
            recipient_name=str(self._latest_transfer_params["recipient_name"]),
            recipient_iban=str(self._latest_transfer_params["recipient_iban"]),
            recipient_bic=self._latest_transfer_params["recipient_bic"],
            purpose=str(self._latest_transfer_params["purpose"]),
            endtoend_id=str(self._latest_transfer_params["endtoend_id"] or "NOTPROVIDED"),
            transfer_overview=self._created_transfer_overview,
        )


CREATED_CLIENTS: list[FakeFinTSClient] = []


def unwrap_response(result):
    if isinstance(result, JSONResponse):
        return result.status_code, json.loads(result.body.decode("utf-8"))
    return 200, result


def make_transfer_payload(**overrides):
    payload = {
        "config": {"scenario": "transfer_success"},
        "source_account": "DE11111111111111111111",
        "account_name": "Max Mustermann",
        "recipient_name": "Quang Hoa Le",
        "recipient_iban": "DE44670800500660521700",
        "amount": "12.34",
        "purpose": "Invoice 42",
    }
    payload.update(overrides)
    return payload
