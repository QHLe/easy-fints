"""Exceptions for backend integration."""

from __future__ import annotations

from typing import Optional

from .models import TanChallenge


class FinTSOperationError(RuntimeError):
    """Base integration error for FinTS operations."""

    def __init__(self, operation: str, message: str):
        super().__init__(f"{operation}: {message}")
        self.operation = operation
        self.message = message


class FinTSConfigError(FinTSOperationError):
    """Raised when required configuration is missing or invalid."""


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
