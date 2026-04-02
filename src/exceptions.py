"""Exceptions for backend integration."""

from __future__ import annotations

from typing import Optional

from .models import TanChallenge, VOPChallenge


class FinTSOperationError(RuntimeError):
    """Base integration error for FinTS operations."""

    def __init__(self, operation: str, message: str):
        super().__init__(f"{operation}: {message}")
        self.operation = operation
        self.message = message


class FinTSConfigError(FinTSOperationError):
    """Raised when required configuration is missing or invalid."""


class FinTSValidationError(FinTSOperationError):
    """Raised when request payload data is invalid before talking to the bank."""

    def __init__(
        self,
        operation: str,
        message: str,
        *,
        field: str | None = None,
        code: str = "validation_error",
    ):
        super().__init__(operation, message)
        self.field = field
        self.code = code


class TanRequiredError(FinTSOperationError):
    """Raised when an operation requires TAN confirmation."""

    def __init__(
        self,
        operation: str,
        challenge: TanChallenge,
        message: Optional[str] = None,
    ):
        super().__init__(operation, message or "TAN confirmation required")
        self.challenge = challenge


class VOPRequiredError(FinTSOperationError):
    """Raised when an operation requires explicit payee-verification approval."""

    def __init__(
        self,
        operation: str,
        challenge: VOPChallenge,
        message: Optional[str] = None,
    ):
        super().__init__(operation, message or "Payee verification approval required")
        self.challenge = challenge
