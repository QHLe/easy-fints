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
    "FinTSClient": ("easy_fints.client", "FinTSClient"),
    "FinTS": ("easy_fints.service", "FinTS"),
    "FinTSConfig": ("easy_fints.models", "FinTSConfig"),
    "AccountSummary": ("easy_fints.models", "AccountSummary"),
    "AccountTransactions": ("easy_fints.models", "AccountTransactions"),
    "TransactionRecord": ("easy_fints.models", "TransactionRecord"),
    "TanChallenge": ("easy_fints.models", "TanChallenge"),
    "TanMethod": ("easy_fints.models", "TanMethod"),
    "TanMethodsSnapshot": ("easy_fints.models", "TanMethodsSnapshot"),
    "TransferResponse": ("easy_fints.models", "TransferResponse"),
    "TransferSummary": ("easy_fints.models", "TransferSummary"),
    "VOPChallenge": ("easy_fints.models", "VOPChallenge"),
    "FinTSOperationError": ("easy_fints.exceptions", "FinTSOperationError"),
    "FinTSConfigError": ("easy_fints.exceptions", "FinTSConfigError"),
    "FinTSValidationError": ("easy_fints.exceptions", "FinTSValidationError"),
    "FinTSCapabilityError": ("easy_fints.exceptions", "FinTSCapabilityError"),
    "TanRequiredError": ("easy_fints.exceptions", "TanRequiredError"),
    "VOPRequiredError": ("easy_fints.exceptions", "VOPRequiredError"),
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
