"""Transfer flows for the FinTS client facade."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from sepaxml import SepaTransfer

from ._client_common import coerce_optional_bool, coerce_optional_date
from .exceptions import FinTSCapabilityError, FinTSOperationError, FinTSValidationError, TanRequiredError, VOPRequiredError
from .helpers import (
    account_label,
    append_operation_log,
    append_operation_step_log,
    compact_iban,
    first_unsupported_sepa_char,
    is_valid_iban,
    list_accounts,
    select_accounts,
)
from .models import TransferResponse, TransferSummary, serialize_value


TRANSFER_MIN_AMOUNT = Decimal("0.01")
TRANSFER_MAX_AMOUNT = Decimal("999999999.99")


class FinTSClientTransferMixin:
    def _build_sepa_transfer_pain_message(
        self,
        *,
        client: Any,
        account_name: str,
        debit_account: Any,
        recipient_name: str,
        recipient_iban: str,
        recipient_bic: Optional[str],
        amount_decimal: Decimal,
        purpose: str,
        endtoend_id: str,
        execution_date: Optional[dt.date],
    ) -> tuple[str, str]:
        version = client._find_supported_sepa_version([
            "pain.001.001.09",
            "pain.001.001.03",
        ])
        config = {
            "name": account_name,
            "IBAN": debit_account.iban,
            "BIC": debit_account.bic,
            "batch": False,
            "currency": "EUR",
        }
        sepa = SepaTransfer(config, version)
        payment: dict[str, Any] = {
            "name": recipient_name,
            "IBAN": recipient_iban,
            "amount": int(amount_decimal * 100),
            "execution_date": execution_date or dt.date(1999, 1, 1),
            "description": purpose,
            "endtoend_id": endtoend_id,
        }
        if recipient_bic:
            payment["BIC"] = recipient_bic
        sepa.add_payment(payment)
        return (
            sepa.export().decode(),
            "urn:iso:std:iso:20022:tech:xsd:" + version,
        )

    def transfer_response_from_result(
        self,
        result: Any,
        params: dict[str, Any],
        *,
        transfer_overview: dict[str, Any] | None = None,
    ) -> TransferResponse:
        try:
            amount_decimal = Decimal(str(params["amount"]))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise FinTSValidationError("transfer", "invalid amount", field="amount") from exc
        overview = transfer_overview if transfer_overview is not None else params.get("transfer_overview")
        return TransferResponse.from_fints_response(
            response=result,
            amount=amount_decimal,
            source_account_label=str((overview or {}).get("source_account_label") or params["source_account"]),
            recipient_name=str(params["recipient_name"]),
            recipient_iban=compact_iban(params["recipient_iban"]),
            recipient_bic=str(params.get("recipient_bic") or "").strip().upper() or None,
            purpose=str(params["purpose"]),
            endtoend_id=str(params.get("endtoend_id") or "NOTPROVIDED"),
            transfer_overview=overview,
        )

    def initiate_transfer(
        self,
        *,
        source_account: str,
        account_name: str,
        recipient_name: str,
        recipient_iban: str,
        recipient_bic: Optional[str],
        amount: str,
        purpose: str,
        endtoend_id: Optional[str] = None,
        instant_payment: Any = False,
        execution_date: Any = None,
    ) -> TransferResponse:
        source_account = str(source_account or "").strip()
        account_name = str(account_name or "").strip()
        recipient_name = str(recipient_name or "").strip()
        recipient_iban = compact_iban(recipient_iban or "")
        recipient_bic = str(recipient_bic or "").strip().upper() or None
        purpose = str(purpose or "").strip()
        endtoend_id = str(endtoend_id or "NOTPROVIDED").strip() or "NOTPROVIDED"
        instant_payment = coerce_optional_bool(
            instant_payment,
            field="instant_payment",
            operation="transfer",
        )
        execution_date_value = coerce_optional_date(
            execution_date,
            field="execution_date",
            operation="transfer",
        )

        if not source_account:
            raise FinTSValidationError("transfer", "missing source_account", field="source_account")
        if not account_name:
            raise FinTSValidationError("transfer", "missing account_name", field="account_name")
        if not recipient_name:
            raise FinTSValidationError("transfer", "missing recipient_name", field="recipient_name")
        if not purpose:
            raise FinTSValidationError("transfer", "missing purpose", field="purpose")
        if not is_valid_iban(recipient_iban):
            raise FinTSValidationError("transfer", "invalid recipient_iban", field="recipient_iban")
        if len(recipient_name) > 70:
            raise FinTSValidationError("transfer", "recipient_name too long (max 70)", field="recipient_name")
        if len(purpose) > 140:
            raise FinTSValidationError("transfer", "purpose too long (max 140)", field="purpose")
        if len(endtoend_id) > 35:
            raise FinTSValidationError("transfer", "endtoend_id too long (max 35)", field="endtoend_id")
        if recipient_bic is not None and len(recipient_bic) not in {8, 11}:
            raise FinTSValidationError("transfer", "invalid recipient_bic", field="recipient_bic")
        if execution_date_value is not None and execution_date_value < dt.date.today():
            raise FinTSValidationError("transfer", "execution_date must be today or later", field="execution_date")
        if instant_payment and execution_date_value is not None:
            raise FinTSValidationError(
                "transfer",
                "instant_payment cannot be combined with execution_date",
                field="instant_payment",
            )
        invalid_purpose_char = first_unsupported_sepa_char(purpose)
        if invalid_purpose_char is not None:
            raise FinTSValidationError(
                "transfer",
                "purpose contains unsupported character "
                f"{invalid_purpose_char!r}; allowed are letters, digits, spaces, and / - ? : ( ) . , ' +",
                field="purpose",
            )

        try:
            amount_decimal = Decimal(str(amount))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise FinTSValidationError("transfer", "invalid amount", field="amount") from exc
        if not amount_decimal.is_finite():
            raise FinTSValidationError("transfer", "invalid amount", field="amount")
        if amount_decimal.as_tuple().exponent < -2:
            raise FinTSValidationError("transfer", "amount must have at most 2 decimal places", field="amount")
        if amount_decimal < TRANSFER_MIN_AMOUNT:
            raise FinTSValidationError("transfer", "amount must be at least 0.01", field="amount")
        if amount_decimal > TRANSFER_MAX_AMOUNT:
            raise FinTSValidationError("transfer", "amount must not exceed 999999999.99", field="amount")

        transfer_params = {
            "source_account": source_account,
            "account_name": account_name,
            "recipient_name": recipient_name,
            "recipient_iban": recipient_iban,
            "recipient_bic": recipient_bic,
            "amount": str(amount_decimal),
            "purpose": purpose,
            "endtoend_id": endtoend_id,
            "instant_payment": instant_payment,
            "execution_date": execution_date_value,
        }
        self._remember_pending_transfer(transfer_params)

        try:
            with self._client_scope() as client:
                append_operation_step_log(
                    "transfer",
                    "started",
                    {
                        "source_account": source_account,
                        "recipient_iban": recipient_iban,
                        "recipient_bic_provided": bool(recipient_bic),
                        "endtoend_id": endtoend_id,
                        "instant_payment": instant_payment,
                        "execution_date": serialize_value(execution_date_value),
                    },
                )
                accounts = select_accounts(self._run("list_accounts", list_accounts, client), source_account)
                if not accounts:
                    raise FinTSValidationError("transfer", "source account not found", field="source_account")
                if len(accounts) > 1:
                    raise FinTSValidationError("transfer", "source account filter is ambiguous", field="source_account")

                debit_account = accounts[0]
                transfer_overview = TransferSummary(
                    source_account_label=account_label(debit_account),
                    recipient_name=recipient_name,
                    recipient_iban=recipient_iban,
                    recipient_bic=recipient_bic,
                    amount=str(amount_decimal),
                    currency="EUR",
                    purpose=purpose,
                    endtoend_id=endtoend_id,
                    instant_payment=instant_payment,
                    execution_date=serialize_value(execution_date_value),
                ).to_dict()
                self._remember_pending_transfer(
                    transfer_params,
                    transfer_overview=transfer_overview,
                )
                transfer_mode = (
                    "scheduled_transfer"
                    if execution_date_value is not None
                    else "instant_payment"
                    if instant_payment
                    else "standard_transfer"
                )
                try:
                    if execution_date_value is None:
                        result = self._run(
                            "transfer",
                            client.simple_sepa_transfer,
                            debit_account,
                            recipient_iban,
                            recipient_bic,
                            recipient_name,
                            amount_decimal,
                            account_name,
                            purpose,
                            instant_payment,
                            endtoend_id,
                            capability_context=transfer_mode,
                        )
                    else:
                        pain_message, pain_descriptor = self._build_sepa_transfer_pain_message(
                            client=client,
                            account_name=account_name,
                            debit_account=debit_account,
                            recipient_name=recipient_name,
                            recipient_iban=recipient_iban,
                            recipient_bic=recipient_bic,
                            amount_decimal=amount_decimal,
                            purpose=purpose,
                            endtoend_id=endtoend_id,
                            execution_date=execution_date_value,
                        )
                        result = self._run(
                            "transfer",
                            client.sepa_transfer,
                            debit_account,
                            pain_message,
                            False,
                            None,
                            "EUR",
                            False,
                            pain_descriptor,
                            instant_payment,
                            capability_context=transfer_mode,
                        )
                except FinTSCapabilityError as exc:
                    self._clear_pending_transfer()
                    raise FinTSCapabilityError(
                        "transfer",
                        transfer_mode,
                        exc.message,
                        execution_date=serialize_value(execution_date_value),
                        instant_payment=instant_payment,
                    ) from exc
                except TanRequiredError as exc:
                    setattr(exc, "transfer_overview", transfer_overview)
                    setattr(exc, "transfer_mode", transfer_mode)
                    raise
                except VOPRequiredError as exc:
                    setattr(exc, "transfer_overview", transfer_overview)
                    setattr(exc, "transfer_mode", transfer_mode)
                    raise
                except FinTSOperationError as exc:
                    self._clear_pending_transfer()
                    if transfer_mode != "standard_transfer" and self._looks_like_transfer_capability_error(exc.message):
                        raise FinTSCapabilityError(
                            "transfer",
                            transfer_mode,
                            exc.message,
                            execution_date=serialize_value(execution_date_value),
                            instant_payment=instant_payment,
                        ) from exc
                    raise

                response = self.transfer_response_from_result(
                    result,
                    {
                        "amount": amount_decimal,
                        "source_account": serialize_value(getattr(debit_account, "iban", None)) or repr(debit_account),
                        "recipient_name": recipient_name,
                        "recipient_iban": recipient_iban,
                        "recipient_bic": recipient_bic,
                        "purpose": purpose,
                        "endtoend_id": endtoend_id,
                        "instant_payment": instant_payment,
                        "execution_date": serialize_value(execution_date_value),
                    },
                    transfer_overview=transfer_overview,
                )
                if not response.success:
                    first_bank_message = None
                    for item in response.bank_responses:
                        if item.get("message"):
                            first_bank_message = str(item["message"])
                            break
                    raise FinTSOperationError(
                        "transfer",
                        self._augment_error_with_bank_response(first_bank_message or "bank rejected transfer"),
                    )
                self._clear_pending_transfer()
                append_operation_log(
                    "transfer",
                    {
                        "source_account": response.source_account_label,
                        "recipient_iban": response.recipient_iban,
                        "status": response.status,
                        "success": response.success,
                        "instant_payment": instant_payment,
                        "execution_date": serialize_value(execution_date_value),
                    },
                )
                return response
        except (TanRequiredError, VOPRequiredError):
            raise
        except Exception:
            self._clear_pending_transfer()
            raise

    def _looks_like_transfer_capability_error(self, message: str) -> bool:
        haystack = message.lower()
        return any(
            marker in haystack
            for marker in (
                "not supported",
                "unsupported",
                "no supported",
                "does not support",
                "not allow",
                "nicht unterstützt",
                "nicht verfug",
                "nicht verfueg",
                "nicht verfügbar",
            )
        )
