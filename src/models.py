"""Serializable models for Python backend integration."""

from __future__ import annotations

import base64
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel

from .helpers import account_label, load_config


def serialize_value(value: Any) -> Any:
    """Convert FinTS values into JSON-friendly primitives."""
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


@dataclass(slots=True)
class FinTSConfig:
    user: str
    pin: str
    server: str
    product_id: str
    bank: Optional[str] = None
    product_name: Optional[str] = None
    product_version: Optional[str] = None
    tan_mechanism: Optional[str] = None
    tan_mechanism_before_bootstrap: bool = False

    def __post_init__(self) -> None:
        if self.tan_mechanism == "":
            self.tan_mechanism = None
        self.tan_mechanism_before_bootstrap = str(
            self.tan_mechanism_before_bootstrap
        ).strip().lower() in {"1", "true", "yes", "on"}

    @classmethod
    def from_env(
        cls,
        env_path: Optional[str] = None,
        overrides: Optional[dict[str, Any]] = None,
    ) -> "FinTSConfig":
        return cls(**load_config(env_path, overrides=overrides))

    def to_client_config(self) -> dict[str, Any]:
        return asdict(self)

    def to_safe_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if data.get("pin"):
            data["pin"] = "***"
        return data


@dataclass(slots=True)
class AccountSummary:
    label: str
    iban: Optional[str]
    bic: Optional[str]
    bank_code: Optional[str]
    account_number: Optional[str]
    subaccount_number: Optional[str]
    bank_identifier: Optional[str]
    balance: Optional[str] = None
    transaction_count: Optional[int] = None
    raw_repr: Optional[str] = None

    @classmethod
    def from_account(
        cls,
        account: Any,
        *,
        balance: Any = None,
        transaction_count: Optional[int] = None,
    ) -> "AccountSummary":
        return cls(
            label=account_label(account),
            iban=getattr(account, "iban", None),
            bic=getattr(account, "bic", None),
            bank_code=getattr(account, "blz", None) or getattr(account, "bank_code", None),
            account_number=getattr(account, "accountnumber", None) or getattr(account, "account", None),
            subaccount_number=getattr(account, "subaccount", None),
            bank_identifier=getattr(account, "bank_identifier", None) or getattr(account, "blz", None),
            balance=serialize_value(balance),
            transaction_count=transaction_count,
            raw_repr=repr(account),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TransactionRecord:
    account_label: str
    tx_index: int
    booking_date: Optional[str]
    value_date: Optional[str]
    amount: Optional[str]
    currency: Optional[str]
    counterparty_name: Optional[str]
    counterparty_iban: Optional[str]
    purpose: Optional[str]
    raw: str

    @classmethod
    def from_row(cls, account_label_value: str, tx_index: int, row: dict[str, Any]) -> "TransactionRecord":
        return cls(
            account_label=account_label_value,
            tx_index=tx_index,
            booking_date=serialize_value(row.get("booking_date")),
            value_date=serialize_value(row.get("value_date")),
            amount=serialize_value(row.get("amount")),
            currency=serialize_value(row.get("currency")),
            counterparty_name=serialize_value(row.get("counterparty_name")),
            counterparty_iban=serialize_value(row.get("counterparty_iban")),
            purpose=serialize_value(row.get("purpose")),
            raw=serialize_value(row.get("raw")) or "",
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AccountTransactions:
    account: AccountSummary
    transactions: list[TransactionRecord]

    def to_dict(self) -> dict[str, Any]:
        return {
            "account": self.account.to_dict(),
            "transactions": [transaction.to_dict() for transaction in self.transactions],
        }


@dataclass(slots=True)
class TanChallenge:
    message: Optional[str]
    decoupled: bool
    has_html: bool
    has_raw: bool
    has_matrix: bool
    has_hhduc: bool
    image_mime_type: Optional[str] = None
    image_base64: Optional[str] = None

    @classmethod
    def from_response(cls, response: Any) -> "TanChallenge":
        challenge_matrix = getattr(response, "challenge_matrix", None)
        image_mime_type = None
        image_base64 = None
        if (
            isinstance(challenge_matrix, tuple)
            and len(challenge_matrix) == 2
            and challenge_matrix[1] is not None
        ):
            image_mime_type = serialize_value(challenge_matrix[0])
            image_base64 = base64.b64encode(challenge_matrix[1]).decode("ascii")
        return cls(
            message=serialize_value(getattr(response, "challenge", None)),
            decoupled=bool(getattr(response, "decoupled", False)),
            has_html=bool(getattr(response, "challenge_html", None)),
            has_raw=bool(getattr(response, "challenge_raw", None)),
            has_matrix=bool(getattr(response, "challenge_matrix", None)),
            has_hhduc=bool(getattr(response, "challenge_hhduc", None)),
            image_mime_type=image_mime_type,
            image_base64=image_base64,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class VOPChallenge:
    result: Optional[str]
    message: Optional[str]
    close_match_name: Optional[str] = None
    other_identification: Optional[str] = None
    na_reason: Optional[str] = None
    raw_repr: Optional[str] = None

    @classmethod
    def from_response(cls, response: Any) -> "VOPChallenge":
        vop_container = getattr(response, "vop_result", None)
        single_result = getattr(vop_container, "vop_single_result", None) or getattr(response, "vop_single_result", None)
        result = serialize_value(getattr(single_result, "result", None))
        close_match_name = serialize_value(getattr(single_result, "close_match_name", None))
        other_identification = serialize_value(getattr(single_result, "other_identification", None))
        na_reason = serialize_value(getattr(single_result, "na_reason", None))

        message = "Review payee verification result before continuing."
        if result == "RVMC":
            message = f"Recipient name partially matches: {close_match_name or 'close match reported by bank'}."
        elif result == "RVNM":
            message = "Recipient name does not match the IBAN according to the bank."
        elif result == "RVNA":
            message = f"Recipient name check not available: {na_reason or 'reason not provided'}."
        elif result == "RCVC":
            message = "Bank requires explicit approval of the payee verification result before execution."

        return cls(
            result=result,
            message=message,
            close_match_name=close_match_name,
            other_identification=other_identification,
            na_reason=na_reason,
            raw_repr=repr(single_result or vop_container or response),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TanMethod:
    code: str
    name: Optional[str]
    security_function: Optional[str]
    identifier: Optional[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TanMethodsSnapshot:
    current: Optional[str]
    current_name: Optional[str]
    methods: list[TanMethod]
    media: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "current": self.current,
            "current_name": self.current_name,
            "methods": [method.to_dict() for method in self.methods],
            "media": self.media,
        }


@dataclass(slots=True)
class TransferResponse:
    status: str
    success: bool
    reference: Optional[str]
    amount: str
    currency: str
    source_account_label: str
    recipient_name: str
    recipient_iban: str
    recipient_bic: Optional[str]
    purpose: str
    endtoend_id: str
    bank_responses: list[dict[str, Any]]

    @classmethod
    def from_fints_response(
        cls,
        *,
        response: Any,
        amount: Decimal,
        source_account_label: str,
        recipient_name: str,
        recipient_iban: str,
        recipient_bic: Optional[str],
        purpose: str,
        endtoend_id: str,
    ) -> "TransferResponse":
        response_status = serialize_value(getattr(getattr(response, "status", None), "name", None)) or "UNKNOWN"
        bank_responses = []
        for item in getattr(response, "responses", []) or []:
            bank_responses.append(
                {
                    "code": serialize_value(getattr(item, "code", None)),
                    "message": serialize_value(getattr(item, "text", None)),
                    "reference": serialize_value(getattr(item, "reference", None)),
                }
            )
        reference = None
        for item in bank_responses:
            if item.get("reference"):
                reference = item["reference"]
                break
        return cls(
            status=response_status,
            success=response_status not in {"ERROR", "UNKNOWN"},
            reference=reference,
            amount=f"{amount:.2f}",
            currency="EUR",
            source_account_label=source_account_label,
            recipient_name=recipient_name,
            recipient_iban=recipient_iban,
            recipient_bic=recipient_bic,
            purpose=purpose,
            endtoend_id=endtoend_id,
            bank_responses=bank_responses,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class StoredBankInfo:
    server: str
    bank_code: str
    product_id: str
    bank_name: Optional[str] = None
    bic: Optional[str] = None
    last_verified_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StoredBankInfo":
        return cls(**data)


@dataclass(slots=True)
class StoredSepaAccount:
    profile_id: str
    iban: Optional[str]
    bic: Optional[str]
    bank_code: Optional[str]
    account_number: Optional[str]
    subaccount_name: Optional[str]
    label: str
    balance: Optional[str] = None
    transaction_count: Optional[int] = None
    raw_repr: Optional[str] = None

    @classmethod
    def from_account_summary(cls, profile_id: str, account: AccountSummary) -> "StoredSepaAccount":
        return cls(
            profile_id=profile_id,
            iban=account.iban,
            bic=account.bic,
            bank_code=account.bank_code or account.bank_identifier,
            account_number=account.account_number,
            subaccount_name=account.subaccount_number,
            label=account.label,
            balance=account.balance,
            transaction_count=account.transaction_count,
            raw_repr=account.raw_repr,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StoredSepaAccount":
        return cls(
            profile_id=data["profile_id"],
            iban=data.get("iban"),
            bic=data.get("bic"),
            bank_code=data.get("bank_code"),
            account_number=data.get("account_number"),
            subaccount_name=data.get("subaccount_name"),
            label=data["label"],
            balance=data.get("balance"),
            transaction_count=data.get("transaction_count"),
            raw_repr=data.get("raw_repr"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class StoredSepaProfile:
    profile_id: str
    server: str
    display_name: Optional[str] = None
    current_tan_method: Optional[str] = None
    current_tan_method_name: Optional[str] = None
    tan_methods: list[dict[str, Any]] | None = None
    accounts: list[StoredSepaAccount] | None = None
    last_successful_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "server": self.server,
            "display_name": self.display_name,
            "current_tan_method": self.current_tan_method,
            "current_tan_method_name": self.current_tan_method_name,
            "tan_methods": self.tan_methods,
            "accounts": [account.to_dict() for account in self.accounts] if self.accounts else [],
            "last_successful_at": self.last_successful_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StoredSepaProfile":
        return cls(
            profile_id=data["profile_id"],
            server=data["server"],
            display_name=data.get("display_name"),
            current_tan_method=data.get("current_tan_method"),
            current_tan_method_name=data.get("current_tan_method_name"),
            tan_methods=data.get("tan_methods"),
            accounts=[StoredSepaAccount.from_dict(item) for item in (data.get("accounts") or [])],
            last_successful_at=data.get("last_successful_at"),
        )

    def to_client_config(
        self,
        bank_info: StoredBankInfo,
        *,
        user_id: str,
        pin: str,
        overrides: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        cfg = {
            "bank": bank_info.bank_code,
            "user": user_id,
            "pin": pin,
            "server": self.server,
            "product_id": bank_info.product_id,
        }
        if overrides:
            cfg.update({key: value for key, value in overrides.items() if value is not None})
        return cfg


class HealthResponseModel(BaseModel):
    status: str


class AccountSummaryResponseModel(BaseModel):
    label: str
    iban: Optional[str]
    bic: Optional[str]
    bank_code: Optional[str]
    account_number: Optional[str]
    subaccount_number: Optional[str]
    bank_identifier: Optional[str]
    balance: Optional[str] = None
    transaction_count: Optional[int] = None
    raw_repr: Optional[str] = None


class TransactionRecordResponseModel(BaseModel):
    account_label: str
    tx_index: int
    booking_date: Optional[str]
    value_date: Optional[str]
    amount: Optional[str]
    currency: Optional[str]
    counterparty_name: Optional[str]
    counterparty_iban: Optional[str]
    purpose: Optional[str]
    raw: str


class AccountTransactionsResponseModel(BaseModel):
    account: AccountSummaryResponseModel
    transactions: list[TransactionRecordResponseModel]


class TanChallengeResponseModel(BaseModel):
    message: Optional[str]
    decoupled: bool
    has_html: bool
    has_raw: bool
    has_matrix: bool
    has_hhduc: bool
    image_mime_type: Optional[str] = None
    image_base64: Optional[str] = None


class VOPChallengeResponseModel(BaseModel):
    result: Optional[str]
    message: Optional[str]
    close_match_name: Optional[str] = None
    other_identification: Optional[str] = None
    na_reason: Optional[str] = None
    raw_repr: Optional[str] = None


class TanRequiredResponseModel(BaseModel):
    error: str
    session_id: str
    state: Optional[str] = None
    next_action: Optional[str] = None
    operation: Optional[str] = None
    message: Optional[str] = None
    challenge: Optional[TanChallengeResponseModel] = None
    vop: Optional[VOPChallengeResponseModel] = None


class ConfirmationPendingResponseModel(BaseModel):
    error: str
    session_id: str
    state: str
    next_action: str
    operation: Optional[str] = None
    message: Optional[str] = None
    challenge: Optional[TanChallengeResponseModel] = None
    vop: Optional[VOPChallengeResponseModel] = None


class ValidationErrorResponseModel(BaseModel):
    error: str
    operation: Optional[str] = None
    field: Optional[str] = None
    message: str


class TransferBankResponseModel(BaseModel):
    code: Optional[str]
    message: Optional[str]
    reference: Optional[str]


class TransferResponseModel(BaseModel):
    status: str
    success: bool
    reference: Optional[str]
    amount: str
    currency: str
    source_account_label: str
    recipient_name: str
    recipient_iban: str
    recipient_bic: Optional[str]
    purpose: str
    endtoend_id: str
    bank_responses: list[TransferBankResponseModel]


class FinTSErrorResponseModel(BaseModel):
    error: str
    operation: str
    message: str


class NotFoundResponseModel(BaseModel):
    error: str
    message: str


class UnknownOperationResponseModel(BaseModel):
    error: str
    message: str
