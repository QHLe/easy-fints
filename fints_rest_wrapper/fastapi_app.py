"""FastAPI REST wrapper for python-fints."""

from __future__ import annotations

import datetime as dt
import logging
import os
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from .client import (
    FinTSClient,
    looks_like_transfer_result,
)
from .diagnostics import summarize_last_bank_response
from .exceptions import (
    FinTSConfigError,
    FinTSCapabilityError,
    FinTSOperationError,
    FinTSValidationError,
    TanRequiredError,
    VOPRequiredError,
)
from .helpers import append_operation_step_log
from .models import (
    AccountSummaryResponseModel,
    AccountTransactionsResponseModel,
    ConfirmationPendingResponseModel,
    FinTSErrorResponseModel,
    HealthResponseModel,
    NotFoundResponseModel,
    SessionCancelResponseModel,
    SessionInfoResponseModel,
    TanRequiredResponseModel,
    UnsupportedTransferProductResponseModel,
    TransferResponseModel,
    UnknownOperationResponseModel,
    ValidationErrorResponseModel,
)


logger = logging.getLogger("pyfin_api")
app = FastAPI()

# In-memory operation sessions.
SESSIONS: dict[str, dict[str, Any]] = {}
DEFAULT_SESSION_TTL_SECONDS = 300
OperationHandler = Callable[[FinTSClient, dict[str, Any]], Any]
SESSION_STATE_RUNNING = "running"
SESSION_STATE_AWAITING_TAN = "awaiting_tan"
SESSION_STATE_AWAITING_DECOUPLED = "awaiting_decoupled"
SESSION_STATE_AWAITING_VOP = "awaiting_vop"
SESSION_STATE_RESUMING = "resuming"
SESSION_STATE_COMPLETED = "completed"
SESSION_STATE_FAILED = "failed"
COMMON_ERROR_RESPONSES = {
    400: {"model": ValidationErrorResponseModel, "description": "Invalid request payload"},
    409: {"model": TanRequiredResponseModel, "description": "TAN challenge required"},
    422: {"model": UnsupportedTransferProductResponseModel, "description": "Unsupported bank transfer product"},
    502: {"model": FinTSErrorResponseModel, "description": "FinTS/provider error"},
}


def _load_session_ttl_seconds() -> int:
    raw_value = os.getenv("FINTS_SESSION_TTL_SECONDS", str(DEFAULT_SESSION_TTL_SECONDS))
    try:
        ttl_seconds = int(str(raw_value).strip())
    except (TypeError, ValueError):
        logger.warning(
            "Invalid FINTS_SESSION_TTL_SECONDS=%r, using default %s",
            raw_value,
            DEFAULT_SESSION_TTL_SECONDS,
        )
        return DEFAULT_SESSION_TTL_SECONDS
    if ttl_seconds <= 0:
        logger.warning(
            "Non-positive FINTS_SESSION_TTL_SECONDS=%r, using default %s",
            raw_value,
            DEFAULT_SESSION_TTL_SECONDS,
        )
        return DEFAULT_SESSION_TTL_SECONDS
    return ttl_seconds


SESSION_TTL = _load_session_ttl_seconds()


def _session_response(status_code: int, **content: Any) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=content)


def _validation_response(
    *,
    message: str,
    field: str | None = None,
    operation: str | None = None,
    code: str = "validation_error",
    status_code: int = 400,
) -> JSONResponse:
    return _session_response(
        status_code,
        error=code,
        operation=operation,
        field=field,
        message=message,
    )


def _capability_response(
    *,
    operation: str,
    product: str,
    message: str,
    execution_date: str | None = None,
    instant_payment: bool | None = None,
) -> JSONResponse:
    return _session_response(
        422,
        error="unsupported_transfer_product",
        operation=operation,
        product=product,
        message=message,
        execution_date=execution_date,
        instant_payment=instant_payment,
    )


def _boolish(value: Any) -> bool:
    if value in (None, ""):
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off", ""}:
            return False
    return bool(value)


def _transfer_overview_from_params(params: dict[str, Any] | None) -> dict[str, Any] | None:
    if not params:
        return None
    existing = params.get("transfer_overview")
    existing_overview = dict(existing) if isinstance(existing, dict) else {}
    source_account_label = (
        params.get("source_account_label")
        or params.get("source_account")
        or existing_overview.get("source_account_label")
    )
    if source_account_label is None:
        return None

    execution_date = params.get("execution_date", existing_overview.get("execution_date"))
    if hasattr(execution_date, "isoformat"):
        execution_date_value = execution_date.isoformat()
    elif execution_date in (None, ""):
        execution_date_value = None
    else:
        execution_date_value = str(execution_date)

    return {
        "source_account_label": str(source_account_label),
        "recipient_name": str(params.get("recipient_name") or existing_overview.get("recipient_name") or ""),
        "recipient_iban": str(params.get("recipient_iban") or existing_overview.get("recipient_iban") or ""),
        "recipient_bic": params.get("recipient_bic", existing_overview.get("recipient_bic")),
        "amount": str(params.get("amount") or existing_overview.get("amount") or ""),
        "currency": "EUR",
        "purpose": str(params.get("purpose") or existing_overview.get("purpose") or ""),
        "endtoend_id": str(
            params.get("endtoend_id")
            or existing_overview.get("endtoend_id")
            or "NOTPROVIDED"
        ),
        "instant_payment": _boolish(
            params.get("instant_payment", existing_overview.get("instant_payment"))
        ),
        "execution_date": execution_date_value,
    }


def _serialize_result(result: Any) -> Any:
    if isinstance(result, list):
        return [item.to_dict() if hasattr(item, "to_dict") else item for item in result]
    if hasattr(result, "to_dict"):
        return result.to_dict()
    return result


def _result_count(result: Any) -> int:
    if isinstance(result, list):
        return len(result)
    return 1 if result is not None else 0


def _session_last_activity(session: dict[str, Any]) -> datetime:
    return session.get("updated_at") or session.get("created_at") or datetime.utcnow()


def _session_expires_at(session: dict[str, Any]) -> datetime:
    return _session_last_activity(session) + timedelta(seconds=SESSION_TTL)


def _session_expires_in_seconds(session: dict[str, Any]) -> int:
    remaining = int((_session_expires_at(session) - datetime.utcnow()).total_seconds())
    return max(0, remaining)


def _session_snapshot(session_id: str, session: dict[str, Any]) -> dict[str, Any]:
    created_at = session.get("created_at") or datetime.utcnow()
    updated_at = session.get("updated_at")
    state = str(session.get("state") or SESSION_STATE_RUNNING)
    return {
        "session_id": session_id,
        "operation": session.get("operation"),
        "state": state,
        "next_action": _next_action_for_state(state),
        "message": session.get("message"),
        "created_at": created_at.isoformat(),
        "updated_at": updated_at.isoformat() if updated_at else None,
        "expires_at": _session_expires_at(session).isoformat(),
        "expires_in_seconds": _session_expires_in_seconds(session),
        "challenge": session.get("challenge"),
        "vop": session.get("vop"),
        "transfer_overview": session.get("transfer_overview"),
    }


def _prune_sessions() -> None:
    if not SESSIONS:
        return
    now = datetime.utcnow()
    expired = [sid for sid, s in SESSIONS.items() if _session_expires_at(s) <= now]
    for sid in expired:
        _close_session(sid)


def _close_session(session_id: str) -> None:
    session = SESSIONS.pop(session_id, None)
    if not session:
        return
    client = session.get("client")
    if client is not None:
        try:
            client.close()
        except Exception:
            pass


def _create_session(client: FinTSClient, operation: str, params: dict[str, Any]) -> str:
    sid = str(uuid.uuid4())
    created_at = datetime.utcnow()
    SESSIONS[sid] = {
        "client": client,
        "operation": operation,
        "params": params,
        "state": SESSION_STATE_RUNNING,
        "created_at": created_at,
        "updated_at": created_at,
    }
    return sid


def _next_action_for_state(state: str) -> str:
    if state == SESSION_STATE_AWAITING_VOP:
        return "approve_vop"
    if state == SESSION_STATE_AWAITING_DECOUPLED:
        return "confirm"
    if state == SESSION_STATE_AWAITING_TAN:
        return "provide_tan"
    return "wait"


def _session_state_from_challenge(challenge: dict[str, Any] | None) -> str:
    if (challenge or {}).get("decoupled"):
        return SESSION_STATE_AWAITING_DECOUPLED
    return SESSION_STATE_AWAITING_TAN


def _mark_session_state(session_id: str, state: str, **updates: Any) -> dict[str, Any] | None:
    session = SESSIONS.get(session_id)
    if session is None:
        return None
    session["state"] = state
    session["updated_at"] = datetime.utcnow()
    session.update(updates)
    return session


def _tan_required_session_response(
    session_id: str,
    *,
    operation: str | None,
    message: str | None,
    challenge: dict[str, Any],
    transfer_overview: dict[str, Any] | None = None,
    status_code: int = 409,
) -> JSONResponse:
    state = _session_state_from_challenge(challenge)
    _mark_session_state(
        session_id,
        state,
        challenge=challenge,
        message=message,
        transfer_overview=transfer_overview,
    )
    return _session_response(
        status_code,
        error="tan_required" if status_code == 409 else "confirmation_pending",
        session_id=session_id,
        state=state,
        next_action=_next_action_for_state(state),
        operation=operation,
        message=message,
        challenge=challenge,
        transfer_overview=transfer_overview,
    )


def _vop_required_session_response(
    session_id: str,
    *,
    operation: str | None,
    message: str | None,
    vop: dict[str, Any],
    transfer_overview: dict[str, Any] | None = None,
    status_code: int = 409,
) -> JSONResponse:
    _mark_session_state(
        session_id,
        SESSION_STATE_AWAITING_VOP,
        vop=vop,
        message=message,
        transfer_overview=transfer_overview,
    )
    return _session_response(
        status_code,
        error="vop_required",
        session_id=session_id,
        state=SESSION_STATE_AWAITING_VOP,
        next_action=_next_action_for_state(SESSION_STATE_AWAITING_VOP),
        operation=operation,
        message=message,
        challenge=None,
        vop=vop,
        transfer_overview=transfer_overview,
    )


@app.get("/health", response_model=HealthResponseModel)
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.on_event("shutdown")
def shutdown_active_sessions() -> None:
    session_ids = list(SESSIONS.keys())
    if session_ids:
        logger.info("Closing %s active session(s) during shutdown", len(session_ids))
        for session_id in session_ids:
            _close_session(session_id)


def _api_config_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    cfg = dict(payload.get("config") or {})
    cfg.pop("product_id", None)
    cfg.pop("product_name", None)
    cfg.pop("product_version", None)
    cfg.pop("tan_mechanism", None)
    cfg.pop("tan_mechanism_before_bootstrap", None)
    return cfg


def _optional_iso_date(value: Any, field_name: str) -> dt.date | None:
    if value in (None, ""):
        return None
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError as exc:
        raise FinTSValidationError(
            "transactions",
            f"invalid {field_name}: expected YYYY-MM-DD",
            field=field_name,
        ) from exc


def _handle_client_operation(
    payload: dict[str, Any],
    *,
    operation: str,
    params: dict[str, Any],
    handler: OperationHandler,
):
    _prune_sessions()
    client: FinTSClient | None = None
    cfg = _api_config_from_payload(payload)

    try:
        client = FinTSClient.from_env(overrides=cfg)
        result = handler(client, params)
        return _serialize_result(result)
    except TanRequiredError as exc:
        if client is None:
            raise HTTPException(status_code=500, detail="client unavailable for TAN session") from exc
        transfer_overview = None
        if operation == "transfer":
            transfer_overview = getattr(exc, "transfer_overview", None)
            if transfer_overview is not None:
                params = dict(params)
                params["transfer_overview"] = transfer_overview
        sid = _create_session(client, operation, params)
        append_operation_step_log(
            operation,
            "challenge_returned",
            {
                "session_id": sid,
                "state": _session_state_from_challenge(exc.challenge.to_dict()),
            },
        )
        return _tan_required_session_response(
            sid,
            operation=exc.operation,
            message=exc.message,
            challenge=exc.challenge.to_dict(),
            transfer_overview=transfer_overview,
        )
    except VOPRequiredError as exc:
        if client is None:
            raise HTTPException(status_code=500, detail="client unavailable for confirmation session") from exc
        transfer_overview = None
        if operation == "transfer":
            transfer_overview = getattr(exc, "transfer_overview", None)
            if transfer_overview is not None:
                params = dict(params)
                params["transfer_overview"] = transfer_overview
        sid = _create_session(client, operation, params)
        append_operation_step_log(
            operation,
            "vop_required",
            {
                "session_id": sid,
                "state": SESSION_STATE_AWAITING_VOP,
                "vop_result": exc.challenge.result,
                "close_match_name": exc.challenge.close_match_name,
                "other_identification": exc.challenge.other_identification,
                "na_reason": exc.challenge.na_reason,
            },
        )
        return _vop_required_session_response(
            sid,
            operation=exc.operation,
            message=exc.message,
            vop=exc.challenge.to_dict(),
            transfer_overview=transfer_overview,
        )
    except FinTSConfigError as exc:
        return _validation_response(message=str(exc), operation=exc.operation, code="config_error")
    except FinTSCapabilityError as exc:
        return _capability_response(
            operation=exc.operation,
            product=exc.product,
            message=exc.message,
            execution_date=exc.execution_date,
            instant_payment=exc.instant_payment,
        )
    except FinTSValidationError as exc:
        return _validation_response(message=exc.message, field=exc.field, operation=exc.operation, code=exc.code)
    except FinTSOperationError as exc:
        return _session_response(
            502,
            error="fints_error",
            operation=exc.operation,
            message=exc.message,
        )


def _accounts_handler(client: FinTSClient, params: dict[str, Any]):
    return client.begin_accounts()


def _balance_handler(client: FinTSClient, params: dict[str, Any]):
    return client.get_account_overview(
        account_filter=params.get("account_filter"),
        include_transaction_count_days=params.get("include_transaction_count_days"),
    )


def _transactions_handler(client: FinTSClient, params: dict[str, Any]):
    return client.list_transactions_by_account(
        account_filter=params.get("account_filter"),
        days=params["days"],
        date_from=params.get("date_from"),
        date_to=params.get("date_to"),
    )


def _transfer_handler(client: FinTSClient, params: dict[str, Any]):
    return client.initiate_transfer(
        source_account=params["source_account"],
        account_name=params["account_name"],
        recipient_name=params["recipient_name"],
        recipient_iban=params["recipient_iban"],
        recipient_bic=params.get("recipient_bic"),
        amount=params["amount"],
        purpose=params["purpose"],
        endtoend_id=params.get("endtoend_id"),
        instant_payment=params.get("instant_payment"),
        execution_date=params.get("execution_date"),
    )


OPERATION_HANDLERS: dict[str, OperationHandler] = {
    "accounts": _accounts_handler,
    "balance": _balance_handler,
    "transactions": _transactions_handler,
    "transfer": _transfer_handler,
}


@app.post("/accounts", response_model=list[AccountSummaryResponseModel], responses=COMMON_ERROR_RESPONSES)
def accounts(payload: dict[str, Any]):
    """Return list of accounts. If operation requires TAN, return 409 with challenge."""
    return _handle_client_operation(
        payload,
        operation="accounts",
        params={},
        handler=OPERATION_HANDLERS["accounts"],
    )


@app.post("/balance", response_model=list[AccountSummaryResponseModel], responses=COMMON_ERROR_RESPONSES)
def balance(payload: dict[str, Any]):
    return _handle_client_operation(
        payload,
        operation="balance",
        params={
            "account_filter": payload.get("account_filter"),
            "include_transaction_count_days": payload.get("include_transaction_count_days"),
        },
        handler=OPERATION_HANDLERS["balance"],
    )


@app.post("/transactions", response_model=list[AccountTransactionsResponseModel], responses=COMMON_ERROR_RESPONSES)
def transactions(payload: dict[str, Any]):
    date_from = _optional_iso_date(payload.get("date_from"), "date_from")
    date_to = _optional_iso_date(payload.get("date_to"), "date_to")
    if date_from is not None and date_to is not None and date_from > date_to:
        return _validation_response(
            message="date_from must be on or before date_to",
            field="date_from",
            operation="transactions",
        )
    return _handle_client_operation(
        payload,
        operation="transactions",
        params={
            "account_filter": payload.get("account_filter"),
            "days": int(payload.get("days", 30)),
            "date_from": date_from,
            "date_to": date_to,
        },
        handler=OPERATION_HANDLERS["transactions"],
    )


@app.post("/transfer", response_model=TransferResponseModel, responses=COMMON_ERROR_RESPONSES)
def transfer(payload: dict[str, Any]):
    execution_date = _optional_iso_date(payload.get("execution_date"), "execution_date")
    if execution_date is not None and execution_date < dt.date.today():
        return _validation_response(
            message="execution_date must be today or later",
            field="execution_date",
            operation="transfer",
        )
    return _handle_client_operation(
        payload,
        operation="transfer",
        params={
            "source_account": payload.get("source_account"),
            "account_name": payload.get("account_name"),
            "recipient_name": payload.get("recipient_name"),
            "recipient_iban": payload.get("recipient_iban"),
            "recipient_bic": payload.get("recipient_bic"),
            "amount": payload.get("amount"),
            "purpose": payload.get("purpose"),
            "endtoend_id": payload.get("endtoend_id"),
            "instant_payment": payload.get("instant_payment"),
            "execution_date": execution_date,
        },
        handler=OPERATION_HANDLERS["transfer"],
    )


def _retry_transfer_with_name_local(payload: dict[str, Any]):
    _prune_sessions()
    session_id = payload.get("session_id")
    recipient_name = str(payload.get("recipient_name") or "").strip()
    if not session_id:
        return _validation_response(message="missing session_id", field="session_id", operation="transfer")
    if not recipient_name:
        return _validation_response(message="missing recipient_name", field="recipient_name", operation="transfer")

    session = SESSIONS.get(session_id)
    if not session:
        return JSONResponse(status_code=404, content={"error": "not_found", "message": "session not found or expired"})
    if session.get("operation") != "transfer":
        return _validation_response(
            message="session does not refer to a transfer operation",
            field="session_id",
            operation="transfer",
        )
    if session.get("state") != SESSION_STATE_AWAITING_VOP:
        return _validation_response(
            message="name correction is only supported while awaiting payee verification",
            field="session_id",
            operation="transfer",
        )

    old_client: FinTSClient = session.get("client")
    params = dict(session.get("params") or {})
    params["recipient_name"] = recipient_name
    transfer_overview = _transfer_overview_from_params(params)
    if transfer_overview is not None:
        params["transfer_overview"] = transfer_overview
    append_operation_step_log(
        "transfer",
        "retry_with_name_requested",
        {
            "session_id": session_id,
            "new_recipient_name": recipient_name,
            "reuse_existing_client": True,
            "has_standing_dialog": bool(old_client._has_standing_dialog()),
        },
    )
    old_client.clear_pending_confirmations()
    _mark_session_state(
        session_id,
        SESSION_STATE_RUNNING,
        params=params,
        challenge=None,
        vop=None,
        message=None,
        retry_with_name=True,
    )

    try:
        result = _transfer_handler(old_client, params)
        _mark_session_state(session_id, SESSION_STATE_COMPLETED)
        _close_session(session_id)
        return _serialize_result(result)
    except TanRequiredError as exc:
        append_operation_step_log(
            "transfer",
            "challenge_returned",
            {
                "session_id": session_id,
                "state": _session_state_from_challenge(exc.challenge.to_dict()),
                "retry_with_name": True,
            },
        )
        return _tan_required_session_response(
            session_id,
            operation=exc.operation,
            message=exc.message,
            challenge=exc.challenge.to_dict(),
            transfer_overview=_transfer_overview_from_params(params),
        )
    except VOPRequiredError as exc:
        append_operation_step_log(
            "transfer",
            "vop_required",
            {
                "session_id": session_id,
                "state": SESSION_STATE_AWAITING_VOP,
                "vop_result": exc.challenge.result,
                "close_match_name": exc.challenge.close_match_name,
                "other_identification": exc.challenge.other_identification,
                "na_reason": exc.challenge.na_reason,
                "retry_with_name": True,
            },
        )
        return _vop_required_session_response(
            session_id,
            operation=exc.operation,
            message=exc.message,
            vop=exc.challenge.to_dict(),
            transfer_overview=_transfer_overview_from_params(params),
        )
    except FinTSValidationError as exc:
        _mark_session_state(session_id, SESSION_STATE_FAILED, message=exc.message)
        _close_session(session_id)
        return _validation_response(message=exc.message, field=exc.field, operation=exc.operation, code=exc.code)
    except FinTSCapabilityError as exc:
        append_operation_step_log(
            "transfer",
            "capability_failed",
            {
                "session_id": session_id,
                "product": exc.product,
                "message": exc.message,
                "execution_date": exc.execution_date,
                "instant_payment": exc.instant_payment,
            },
        )
        _mark_session_state(session_id, SESSION_STATE_FAILED, message=exc.message)
        _close_session(session_id)
        return _capability_response(
            operation=exc.operation,
            product=exc.product,
            message=exc.message,
            execution_date=exc.execution_date,
            instant_payment=exc.instant_payment,
        )
    except FinTSOperationError as exc:
        append_operation_step_log(
            "transfer",
            "retry_with_name_failed",
            {
                "session_id": session_id,
                "message": exc.message,
                "bank_response": summarize_last_bank_response(),
            },
        )
        _mark_session_state(session_id, SESSION_STATE_FAILED, message=exc.message)
        _close_session(session_id)
        return _session_response(
            502,
            error="fints_error",
            operation=exc.operation,
            message=exc.message,
        )


@app.post(
    "/transfer/retry-with-name",
    response_model=TransferResponseModel | ConfirmationPendingResponseModel | TanRequiredResponseModel | UnsupportedTransferProductResponseModel,
    responses={
        400: {"model": ValidationErrorResponseModel, "description": "Invalid request payload"},
        404: {"model": NotFoundResponseModel, "description": "Session not found or expired"},
        409: {"model": TanRequiredResponseModel, "description": "Further confirmation required"},
        422: {"model": UnsupportedTransferProductResponseModel, "description": "Unsupported bank transfer product"},
        502: {"model": FinTSErrorResponseModel, "description": "FinTS/provider error"},
    },
)
def retry_transfer_with_name(payload: dict[str, Any]):
    session_id = str(payload.get("session_id") or "").strip()
    if not session_id:
        return _validation_response(message="missing session_id", field="session_id", operation="transfer")
    return _retry_transfer_with_name_local(payload)


def _get_session_local(session_id: str):
    _prune_sessions()
    session = SESSIONS.get(session_id)
    if not session:
        return JSONResponse(status_code=404, content={"error": "not_found", "message": "session not found or expired"})
    return _session_response(200, **_session_snapshot(session_id, session))


@app.get(
    "/sessions/{session_id}",
    response_model=SessionInfoResponseModel | NotFoundResponseModel,
    responses={
        404: {"model": NotFoundResponseModel, "description": "Session not found or expired"},
    },
)
def get_session(session_id: str):
    return _get_session_local(session_id)


def _cancel_session_local(session_id: str):
    _prune_sessions()
    session = SESSIONS.get(session_id)
    if not session:
        return JSONResponse(status_code=404, content={"error": "not_found", "message": "session not found or expired"})

    append_operation_step_log(
        "session",
        "cancel_requested",
        {
            "session_id": session_id,
            "operation": session.get("operation"),
            "state": session.get("state"),
        },
    )
    operation = session.get("operation")
    _close_session(session_id)
    append_operation_step_log(
        "session",
        "cancel_completed",
        {
            "session_id": session_id,
            "operation": operation,
        },
    )
    return _session_response(
        200,
        status="cancelled",
        session_id=session_id,
        operation=operation,
        message="session cancelled",
    )


@app.delete(
    "/sessions/{session_id}",
    response_model=SessionCancelResponseModel | NotFoundResponseModel,
    responses={
        404: {"model": NotFoundResponseModel, "description": "Session not found or expired"},
    },
)
def cancel_session(session_id: str):
    return _cancel_session_local(session_id)


def _confirm_local(payload: dict[str, Any]):
    _prune_sessions()
    session_id = payload.get("session_id")
    tan = payload.get("tan", "")
    approve_vop = bool(payload.get("approve_vop"))
    append_operation_step_log(
        "confirm",
        "request_received",
        {
            "session_id": session_id,
            "tan_provided": bool(tan),
            "approve_vop": approve_vop,
        },
    )
    if not session_id:
        return _validation_response(message="missing session_id", field="session_id", operation="confirm")

    session = SESSIONS.get(session_id)
    if not session:
        append_operation_step_log(
            "confirm",
            "failed",
            {
                "session_id": session_id,
                "reason": "session not found or expired",
                "bank_response": summarize_last_bank_response(),
            },
        )
        return JSONResponse(status_code=404, content={"error": "not_found", "message": "session not found or expired"})

    client: FinTSClient = session.get("client")
    operation = session.get("operation")
    params = session.get("params") or {}
    session_state = session.get("state")
    append_operation_step_log(
        "confirm",
        "session_loaded",
        {
            "session_id": session_id,
            "resume_operation": operation,
            "session_state": session_state,
            "has_pending_tan": bool(getattr(client, "_pending_tan_response", None)),
            "has_pending_vop": bool(getattr(client, "_pending_vop_response", None)),
        },
    )

    selected_action = "confirm_pending"
    if session_state == SESSION_STATE_AWAITING_VOP or getattr(client, "_pending_vop_response", None) is not None:
        selected_action = "approve_vop"
    _mark_session_state(session_id, SESSION_STATE_RUNNING, last_action=selected_action)
    try:
        if selected_action == "approve_vop":
            if not approve_vop:
                return _validation_response(
                    message="approve_vop must be true before continuing this transfer",
                    field="approve_vop",
                    operation="confirm",
                )
            chall, vop, submit_result = client.approve_vop()
        else:
            chall, vop, submit_result = client.confirm_pending(tan)
    except FinTSCapabilityError as exc:
        append_operation_step_log(
            "confirm",
            "capability_failed",
            {
                "session_id": session_id,
                "resume_operation": operation,
                "product": exc.product,
                "message": exc.message,
                "execution_date": exc.execution_date,
                "instant_payment": exc.instant_payment,
            },
        )
        _mark_session_state(session_id, SESSION_STATE_FAILED, message=exc.message)
        _close_session(session_id)
        return _capability_response(
            operation=exc.operation,
            product=exc.product,
            message=exc.message,
            execution_date=exc.execution_date,
            instant_payment=exc.instant_payment,
        )
    except FinTSOperationError as exc:
        append_operation_step_log(
            "confirm",
            "failed",
            {
                "session_id": session_id,
                "operation": exc.operation,
                "message": exc.message,
                "selected_action": selected_action,
                "bank_response": summarize_last_bank_response(),
            },
        )
        _mark_session_state(session_id, SESSION_STATE_FAILED, message=exc.message)
        _close_session(session_id)
        return _session_response(
            502,
            error="fints_error",
            operation=exc.operation,
            message=exc.message,
        )
    if chall:
        challenge = chall.to_dict()
        state = _session_state_from_challenge(challenge)
        append_operation_step_log(
            "confirm",
            "challenge_returned",
            {
                "session_id": session_id,
                "resume_operation": operation,
                "state": state,
            },
        )
        return _tan_required_session_response(
            session_id,
            operation=operation,
            message=challenge.get("message"),
            challenge=challenge,
            transfer_overview=_transfer_overview_from_params(params),
            status_code=202 if state == SESSION_STATE_AWAITING_DECOUPLED else 409,
        )

    if vop:
        vop_payload = vop.to_dict()
        append_operation_step_log(
            "confirm",
            "vop_required",
            {
                "session_id": session_id,
                "resume_operation": operation,
                "selected_action": selected_action,
                "vop_result": vop_payload.get("result"),
                "close_match_name": vop_payload.get("close_match_name"),
                "other_identification": vop_payload.get("other_identification"),
                "na_reason": vop_payload.get("na_reason"),
            },
        )
        return _vop_required_session_response(
            session_id,
            operation=operation,
            message=vop_payload.get("message"),
            vop=vop_payload,
            transfer_overview=_transfer_overview_from_params(params),
        )

    if submit_result is not None and operation == "transfer" and looks_like_transfer_result(submit_result):
        transfer_result = client.transfer_response_from_result(
            submit_result,
            params,
            transfer_overview=_transfer_overview_from_params(params),
        )
        append_operation_step_log(
            "confirm",
            "resume_completed",
            {
                "session_id": session_id,
                "resume_operation": operation,
                "result_count": 1,
                "selected_action": selected_action,
                "submit_result_type": type(submit_result).__name__,
            },
        )
        _mark_session_state(session_id, SESSION_STATE_COMPLETED)
        _close_session(session_id)
        return _serialize_result(transfer_result)

    append_operation_step_log(
        "confirm",
        "resume_deferred",
        {
            "session_id": session_id,
            "resume_operation": operation,
            "selected_action": selected_action,
            "submit_result_type": None if submit_result is None else type(submit_result).__name__,
        },
    )

    _mark_session_state(session_id, SESSION_STATE_RESUMING)
    append_operation_step_log(
        "confirm",
        "resume_started",
        {
            "session_id": session_id,
            "resume_operation": operation,
        },
    )
    try:
        handler = OPERATION_HANDLERS.get(operation)
        if handler is None:
            append_operation_step_log(
                "confirm",
                "failed",
                {
                    "session_id": session_id,
                    "resume_operation": operation,
                    "reason": "unknown session operation",
                    "bank_response": summarize_last_bank_response(),
                },
            )
            _mark_session_state(session_id, SESSION_STATE_FAILED, message="Unknown session operation")
            _close_session(session_id)
            return _session_response(
                500,
                error="unknown_operation",
                message="Unknown session operation",
            )

        result = handler(client, params)
        append_operation_step_log(
            "confirm",
            "resume_completed",
            {
                "session_id": session_id,
                "resume_operation": operation,
                "result_count": _result_count(result),
            },
        )
        _mark_session_state(session_id, SESSION_STATE_COMPLETED)
        _close_session(session_id)
        return _serialize_result(result)
    except TanRequiredError as exc:
        append_operation_step_log(
            "confirm",
            "challenge_returned",
            {
                "session_id": session_id,
                "resume_operation": operation,
            },
        )
        return _tan_required_session_response(
            session_id,
            operation=exc.operation,
            message=exc.message,
            challenge=exc.challenge.to_dict(),
            transfer_overview=_transfer_overview_from_params(params) if operation == "transfer" else None,
        )
    except VOPRequiredError as exc:
        append_operation_step_log(
            "confirm",
            "vop_required",
            {
                "session_id": session_id,
                "resume_operation": operation,
                "vop_result": exc.challenge.result,
                "close_match_name": exc.challenge.close_match_name,
                "other_identification": exc.challenge.other_identification,
                "na_reason": exc.challenge.na_reason,
            },
        )
        return _vop_required_session_response(
            session_id,
            operation=exc.operation,
            message=exc.message,
            vop=exc.challenge.to_dict(),
            transfer_overview=_transfer_overview_from_params(params) if operation == "transfer" else None,
        )
    except FinTSValidationError as exc:
        append_operation_step_log(
            "confirm",
            "failed",
            {
                "session_id": session_id,
                "resume_operation": operation,
                "operation": exc.operation,
                "message": exc.message,
            },
        )
        _mark_session_state(session_id, SESSION_STATE_FAILED, message=exc.message)
        _close_session(session_id)
        return _validation_response(message=exc.message, field=exc.field, operation=exc.operation, code=exc.code)
    except FinTSOperationError as exc:
        append_operation_step_log(
            "confirm",
            "failed",
            {
                "session_id": session_id,
                "resume_operation": operation,
                "operation": exc.operation,
                "message": exc.message,
                "bank_response": summarize_last_bank_response(),
            },
        )
        _mark_session_state(session_id, SESSION_STATE_FAILED, message=exc.message)
        _close_session(session_id)
        return _session_response(
            502,
            error="fints_error",
            operation=exc.operation,
            message=exc.message,
        )


@app.post(
    "/confirm",
    response_model=list[AccountSummaryResponseModel] | list[AccountTransactionsResponseModel] | TransferResponseModel | ConfirmationPendingResponseModel | UnsupportedTransferProductResponseModel,
    responses={
        400: {"model": ValidationErrorResponseModel, "description": "Invalid request payload"},
        404: {"model": NotFoundResponseModel, "description": "Session not found or expired"},
        409: {"model": TanRequiredResponseModel, "description": "TAN challenge required"},
        500: {"model": UnknownOperationResponseModel, "description": "Unknown session operation"},
        422: {"model": UnsupportedTransferProductResponseModel, "description": "Unsupported bank transfer product"},
        502: {"model": FinTSErrorResponseModel, "description": "FinTS/provider error"},
    },
)
def confirm(payload: dict[str, Any]):
    session_id = str(payload.get("session_id") or "").strip()
    if not session_id:
        return _validation_response(message="missing session_id", field="session_id", operation="confirm")
    return _confirm_local(payload)
