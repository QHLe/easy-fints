"""FastAPI REST wrapper for python-fints."""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from .client import PyFinIntegrationClient
from .diagnostics import summarize_last_bank_response
from .exceptions import FinTSConfigError, FinTSOperationError, TanRequiredError
from .helpers import append_operation_step_log


app = FastAPI()

# In-memory TAN sessions: session_id -> dict with keys 'client','operation','params','created_at'
SESSIONS: dict[str, dict[str, Any]] = {}
SESSION_TTL = int(os.getenv("PYFIN_SESSION_TTL", "300"))  # seconds
OperationHandler = Callable[[PyFinIntegrationClient, dict[str, Any]], Any]


def _session_response(status_code: int, **content: Any) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=content)


def _prune_sessions() -> None:
    if not SESSIONS:
        return
    now = datetime.utcnow()
    expired = [sid for sid, s in SESSIONS.items() if (now - s.get("created_at", now)) > timedelta(seconds=SESSION_TTL)]
    for sid in expired:
        try:
            sess = SESSIONS.pop(sid, None)
            if sess and sess.get("client"):
                try:
                    sess["client"].close()
                except Exception:
                    pass
        except Exception:
            pass


def _create_session(client: PyFinIntegrationClient, operation: str, params: dict[str, Any]) -> str:
    sid = str(uuid.uuid4())
    SESSIONS[sid] = {
        "client": client,
        "operation": operation,
        "params": params,
        "created_at": datetime.utcnow(),
    }
    return sid


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _env_path_from_payload(payload: dict[str, Any]) -> str | None:
    return payload.get("env_path") if payload.get("env_path") is not None else None


def _handle_client_operation(
    payload: dict[str, Any],
    *,
    operation: str,
    params: dict[str, Any],
    handler: OperationHandler,
):
    _prune_sessions()
    client: PyFinIntegrationClient | None = None
    cfg = payload.get("config") or {}

    try:
        client = PyFinIntegrationClient.from_env(_env_path_from_payload(payload), overrides=cfg)
        result = handler(client, params)
        return [item.to_dict() for item in result]
    except TanRequiredError as exc:
        if client is None:
            raise HTTPException(status_code=500, detail="client unavailable for TAN session") from exc
        sid = _create_session(client, operation, params)
        return _session_response(
            409,
            error="tan_required",
            session_id=sid,
            operation=exc.operation,
            message=exc.message,
            challenge=exc.challenge.to_dict(),
        )
    except FinTSConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except FinTSOperationError as exc:
        return _session_response(
            502,
            error="fints_error",
            operation=exc.operation,
            message=exc.message,
        )


def _accounts_handler(client: PyFinIntegrationClient, params: dict[str, Any]):
    return client.begin_accounts(account_filter=params.get("account_filter"))


def _balance_handler(client: PyFinIntegrationClient, params: dict[str, Any]):
    return client.get_account_overview(
        account_filter=params.get("account_filter"),
        include_transaction_count_days=params.get("include_transaction_count_days"),
    )


def _transactions_handler(client: PyFinIntegrationClient, params: dict[str, Any]):
    return client.list_transactions_by_account(
        account_filter=params.get("account_filter"),
        days=params["days"],
    )


OPERATION_HANDLERS: dict[str, OperationHandler] = {
    "accounts": _accounts_handler,
    "balance": _balance_handler,
    "transactions": _transactions_handler,
}


@app.post("/accounts")
def accounts(payload: dict[str, Any]):
    """Return list of accounts. If operation requires TAN, return 409 with challenge."""
    return _handle_client_operation(
        payload,
        operation="accounts",
        params={"account_filter": payload.get("account_filter")},
        handler=OPERATION_HANDLERS["accounts"],
    )


@app.post("/balance")
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


@app.post("/transactions")
def transactions(payload: dict[str, Any]):
    return _handle_client_operation(
        payload,
        operation="transactions",
        params={
            "account_filter": payload.get("account_filter"),
            "days": int(payload.get("days", 30)),
        },
        handler=OPERATION_HANDLERS["transactions"],
    )


@app.post("/submit-tan")
def submit_tan(payload: dict[str, Any]):
    _prune_sessions()
    session_id = payload.get("session_id")
    tan = payload.get("tan", "")
    append_operation_step_log(
        "submit_tan",
        "request_received",
        {
            "session_id": session_id,
            "tan_provided": bool(tan),
        },
    )
    if not session_id:
        raise HTTPException(status_code=400, detail="missing session_id")

    session = SESSIONS.get(session_id)
    if not session:
        append_operation_step_log(
            "submit_tan",
            "failed",
            {
                "session_id": session_id,
                "reason": "session not found or expired",
                "bank_response": summarize_last_bank_response(),
            },
        )
        return JSONResponse(status_code=404, content={"error": "not_found", "message": "session not found or expired"})

    client: PyFinIntegrationClient = session.get("client")
    try:
        chall = client.submit_tan(tan)
    except FinTSOperationError as exc:
        append_operation_step_log(
            "submit_tan",
            "failed",
            {
                "session_id": session_id,
                "operation": exc.operation,
                "message": exc.message,
                "bank_response": summarize_last_bank_response(),
            },
        )
        SESSIONS.pop(session_id, None)
        return _session_response(
            502,
            error="fints_error",
            operation=exc.operation,
            message=exc.message,
        )

    if chall:
        return _session_response(
            409,
            error="tan_required",
            session_id=session_id,
            operation=session.get("operation"),
            challenge=chall.to_dict(),
        )

    operation = session.get("operation")
    params = session.get("params") or {}
    append_operation_step_log(
        "submit_tan",
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
                "submit_tan",
                "failed",
                {
                    "session_id": session_id,
                    "resume_operation": operation,
                    "reason": "unknown session operation",
                    "bank_response": summarize_last_bank_response(),
                },
            )
            SESSIONS.pop(session_id, None)
            return _session_response(
                500,
                error="unknown_operation",
                message="Unknown session operation",
            )

        result = handler(client, params)
        append_operation_step_log(
            "submit_tan",
            "resume_completed",
            {
                "session_id": session_id,
                "resume_operation": operation,
                "result_count": len(result),
            },
        )
        SESSIONS.pop(session_id, None)
        return [item.to_dict() for item in result]
    except TanRequiredError as exc:
        new_sid = _create_session(client, operation, params)
        append_operation_step_log(
            "submit_tan",
            "challenge_returned",
            {
                "session_id": session_id,
                "resume_operation": operation,
                "new_session_id": new_sid,
                "message": exc.message,
            },
        )
        return _session_response(
            409,
            error="tan_required",
            session_id=new_sid,
            operation=exc.operation,
            message=exc.message,
            challenge=exc.challenge.to_dict(),
        )
    except FinTSOperationError as exc:
        append_operation_step_log(
            "submit_tan",
            "failed",
            {
                "session_id": session_id,
                "resume_operation": operation,
                "operation": exc.operation,
                "message": exc.message,
                "bank_response": summarize_last_bank_response(),
            },
        )
        SESSIONS.pop(session_id, None)
        return _session_response(
            502,
            error="fints_error",
            operation=exc.operation,
            message=exc.message,
        )
