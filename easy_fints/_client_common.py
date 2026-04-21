"""Shared helpers for the public FinTS client facade."""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any, Optional

import fints.exceptions as fints_exceptions
from fints.client import NeedTANResponse, NeedVOPResponse
from fints.formals import CUSTOMER_ID_ANONYMOUS

from .diagnostics import summarize_last_bank_response
from .exceptions import FinTSOperationError, FinTSValidationError
from .helpers import create_client
from .models import BankInfo, TanMethod, TanMethodsSnapshot, serialize_value


logger = logging.getLogger("pyfin_client")


def augment_error_with_bank_response(message: str) -> str:
    summary = summarize_last_bank_response()
    if not summary:
        return message
    return f"{message} (bank response: {summary})"


def looks_like_tan_required(value: Any) -> bool:
    """Best-effort detection for NeedTANResponse-like values."""
    return isinstance(value, NeedTANResponse) or any(
        hasattr(value, attr)
        for attr in ("challenge", "challenge_html", "challenge_raw", "challenge_matrix")
    )


def looks_like_vop_required(value: Any) -> bool:
    """Best-effort detection for NeedVOPResponse-like values."""
    return isinstance(value, NeedVOPResponse) or (
        not looks_like_tan_required(value)
        and hasattr(value, "vop_result")
        and hasattr(value, "command_seg")
        and hasattr(value, "resume_method")
    )


def looks_like_transfer_result(value: Any) -> bool:
    """Detect TransactionResponse-like objects returned after transfer submission."""
    responses = getattr(value, "responses", None)
    return hasattr(value, "status") and responses is not None and not callable(responses)


def coerce_optional_bool(value: Any, *, field: str, operation: str) -> bool:
    """Parse a bool-like request value while accepting common JSON/env-style forms."""
    if value is None or value == "":
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
    raise FinTSValidationError(operation, f"invalid {field}", field=field)


def coerce_optional_date(value: Any, *, field: str, operation: str) -> Optional[dt.date]:
    if value in (None, ""):
        return None
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        try:
            return dt.date.fromisoformat(value)
        except ValueError as exc:
            raise FinTSValidationError(operation, f"invalid {field}: expected YYYY-MM-DD", field=field) from exc
    raise FinTSValidationError(operation, f"invalid {field}: expected YYYY-MM-DD", field=field)


def _supported_operations_to_dict(value: Any) -> dict[str, bool]:
    result: dict[str, bool] = {}
    for key, enabled in (value or {}).items() if hasattr(value, "items") else []:
        name = str(getattr(key, "name", None) or key)
        result[name] = bool(enabled)
    return result


def _supported_formats_to_dict(value: Any) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for key, formats in (value or {}).items() if hasattr(value, "items") else []:
        name = str(getattr(key, "name", None) or key)
        result[name] = [str(item) for item in (formats or [])]
    return result


def _tan_methods_snapshot_from_low_level_client(client: Any) -> TanMethodsSnapshot:
    raw_methods = getattr(client, "get_tan_mechanisms", lambda: {})() or {}
    current = getattr(client, "get_current_tan_mechanism", lambda: None)()
    current_name = None
    methods = []
    for code, method in raw_methods.items() if hasattr(raw_methods, "items") else []:
        method_name = serialize_value(getattr(method, "name", None))
        methods.append(
            TanMethod(
                code=str(code),
                name=method_name,
                security_function=serialize_value(getattr(method, "security_function", None)),
                identifier=serialize_value(getattr(method, "identifier", None)),
            )
        )
        if str(code) == str(current):
            current_name = method_name

    # The anonymous bootstrap path in python-fints seeds "999" before any real
    # method metadata is available. Avoid surfacing that placeholder as if it
    # were a bank-advertised current TAN mechanism.
    if not methods or str(current) not in {method.code for method in methods}:
        current = None
        current_name = None

    return TanMethodsSnapshot(
        current=serialize_value(current),
        current_name=current_name,
        methods=methods,
        media=None,
    )


def lookup_bank_info(
    *,
    bank: str,
    server: str,
    product_id: str,
    product_name: Optional[str] = None,
    product_version: Optional[str] = None,
) -> BankInfo:
    client = create_client(
        {
            "bank": bank,
            "user": CUSTOMER_ID_ANONYMOUS,
            "pin": None,
            "server": server,
            "product_id": product_id,
            "product_name": product_name,
            "product_version": product_version,
        }
    )

    try:
        with client:
            pass

        try:
            client.fetch_tan_mechanisms()
        except Exception as exc:
            logger.info("Anonymous TAN mechanism fetch for bank info failed: %s", exc)

        info = client.get_information() or {}
        bank_section = info.get("bank") if isinstance(info, dict) else {}
        return BankInfo(
            bank_code=str(bank),
            server=str(server),
            bank_name=serialize_value((bank_section or {}).get("name")),
            supported_operations=_supported_operations_to_dict((bank_section or {}).get("supported_operations")),
            supported_formats=_supported_formats_to_dict((bank_section or {}).get("supported_formats")),
            supported_sepa_formats=[str(item) for item in ((bank_section or {}).get("supported_sepa_formats") or [])],
            tan_methods=_tan_methods_snapshot_from_low_level_client(client),
        )
    except Exception as exc:
        logger.exception("Exception while fetching anonymous bank info")
        if getattr(fints_exceptions, "FinTSDialogInitError", None) and isinstance(
            exc, fints_exceptions.FinTSDialogInitError
        ):
            raise FinTSOperationError(
                "bank_info",
                augment_error_with_bank_response(
                    f"Dialog initialization failed: {exc}"
                ),
            ) from exc
        raise FinTSOperationError("bank_info", augment_error_with_bank_response(str(exc))) from exc
