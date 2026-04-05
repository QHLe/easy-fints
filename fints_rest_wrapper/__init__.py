"""Public package API for REST-server and library-style integration."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .client import FinTSClient
    from .exceptions import (
        FinTSCapabilityError,
        FinTSConfigError,
        FinTSOperationError,
        FinTSValidationError,
        TanRequiredError,
        VOPRequiredError,
    )
    from .models import (
        AccountSummary,
        AccountTransactions,
        FinTSConfig,
        TanChallenge,
        TanMethod,
        TanMethodsSnapshot,
        TransferResponse,
        TransferSummary,
        TransactionRecord,
        VOPChallenge,
    )
    from .service import FinTS


_EXPORT_MAP = {
    "FinTSClient": ("fints_rest_wrapper.client", "FinTSClient"),
    "FinTS": ("fints_rest_wrapper.service", "FinTS"),
    "FinTSConfig": ("fints_rest_wrapper.models", "FinTSConfig"),
    "AccountSummary": ("fints_rest_wrapper.models", "AccountSummary"),
    "AccountTransactions": ("fints_rest_wrapper.models", "AccountTransactions"),
    "TransactionRecord": ("fints_rest_wrapper.models", "TransactionRecord"),
    "TanChallenge": ("fints_rest_wrapper.models", "TanChallenge"),
    "TanMethod": ("fints_rest_wrapper.models", "TanMethod"),
    "TanMethodsSnapshot": ("fints_rest_wrapper.models", "TanMethodsSnapshot"),
    "TransferResponse": ("fints_rest_wrapper.models", "TransferResponse"),
    "TransferSummary": ("fints_rest_wrapper.models", "TransferSummary"),
    "VOPChallenge": ("fints_rest_wrapper.models", "VOPChallenge"),
    "FinTSOperationError": ("fints_rest_wrapper.exceptions", "FinTSOperationError"),
    "FinTSConfigError": ("fints_rest_wrapper.exceptions", "FinTSConfigError"),
    "FinTSValidationError": ("fints_rest_wrapper.exceptions", "FinTSValidationError"),
    "FinTSCapabilityError": ("fints_rest_wrapper.exceptions", "FinTSCapabilityError"),
    "TanRequiredError": ("fints_rest_wrapper.exceptions", "TanRequiredError"),
    "VOPRequiredError": ("fints_rest_wrapper.exceptions", "VOPRequiredError"),
}

__all__ = sorted(_EXPORT_MAP)


def __getattr__(name: str) -> Any:
    try:
        module_name, attr_name = _EXPORT_MAP[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
