"""Confirmation and resume flows for the FinTS client facade."""

from __future__ import annotations

import logging
from typing import Any, Optional

from ._client_common import looks_like_tan_required, looks_like_vop_required
from .diagnostics import summarize_last_bank_response
from .exceptions import FinTSOperationError, TanRequiredError, VOPRequiredError
from .helpers import append_operation_log, append_operation_step_log
from .models import TanChallenge, VOPChallenge


logger = logging.getLogger("pyfin_client")


class FinTSClientConfirmationMixin:
    def confirm_pending(self, tan: str = "") -> tuple[Optional[TanChallenge], Optional[VOPChallenge], Any]:
        append_operation_step_log(
            "confirm_pending",
            "started",
            {
                "client_open": self._client is not None,
                "has_pending_tan": self._pending_tan_response is not None,
                "has_pending_vop": self._pending_vop_response is not None,
                "tan_provided": bool(tan),
            },
        )
        if self._client is None:
            append_operation_step_log(
                "confirm_pending",
                "failed",
                {
                    "reason": "client is not open",
                    "bank_response": summarize_last_bank_response(),
                },
            )
            raise FinTSOperationError("confirm_pending", "client is not open")
        if self._pending_tan_response is None:
            append_operation_step_log(
                "confirm_pending",
                "failed",
                {
                    "reason": "no pending TAN challenge",
                    "bank_response": summarize_last_bank_response(),
                },
            )
            raise FinTSOperationError("confirm_pending", "no pending TAN challenge")

        try:
            with self._client_scope():
                logger.info("Submitting TAN for pending challenge (masked)")
                result = self._client.send_tan(self._pending_tan_response, tan)
        except TanRequiredError as exc:
            append_operation_step_log(
                "confirm_pending",
                "challenge_returned",
                {"decoupled": exc.challenge.decoupled},
            )
            self._pending_tan_response = getattr(self._client, "init_tan_response", None) or self._pending_tan_response
            return (exc.challenge, None, None)
        except VOPRequiredError as exc:
            append_operation_step_log(
                "confirm_pending",
                "vop_required",
                {
                    "result": exc.challenge.result,
                },
            )
            self._pending_tan_response = None
            self._pending_vop_response = self._pending_vop_response
            return (None, exc.challenge, None)
        except Exception as exc:
            logger.exception("Exception while submitting TAN")
            append_operation_step_log(
                "confirm_pending",
                "failed",
                {
                    "reason": str(exc),
                    "bank_response": summarize_last_bank_response(),
                },
            )
            if looks_like_tan_required(exc):
                self._pending_tan_response = exc
                return (TanChallenge.from_response(exc), None, None)
            if looks_like_vop_required(exc):
                self._pending_tan_response = None
                self._pending_vop_response = exc
                return (None, VOPChallenge.from_response(exc), None)
            raise FinTSOperationError("confirm_pending", str(exc)) from exc

        if looks_like_tan_required(result):
            tan = TanChallenge.from_response(result)
            self._pending_tan_response = result
            self._pending_vop_response = None
            append_operation_step_log(
                "confirm_pending",
                "challenge_returned",
                {"decoupled": tan.decoupled},
            )
            return (tan, None, None)
        if looks_like_vop_required(result):
            self._pending_tan_response = None
            self._pending_vop_response = result
            vop = VOPChallenge.from_response(result)
            append_operation_step_log(
                "confirm_pending",
                "vop_required",
                {
                    "result": vop.result,
                },
            )
            return (None, vop, None)

        self._pending_tan_response = None
        self._pending_vop_response = None
        if getattr(self._client, "init_tan_response", None) is not None:
            self._client.init_tan_response = None
        try:
            result = self._finalize_pending_transfer_result(result)
        except TanRequiredError as exc:
            self._pending_tan_response = getattr(self._client, "init_tan_response", None) or self._pending_tan_response
            return (exc.challenge, None, None)
        except VOPRequiredError as exc:
            return (None, exc.challenge, None)
        append_operation_log(
            "confirm_pending",
            {"status": "completed", "result_type": type(result).__name__},
        )
        return (None, None, result)

    def approve_vop(self) -> tuple[Optional[TanChallenge], Optional[VOPChallenge], Any]:
        append_operation_step_log(
            "approve_vop",
            "started",
            {
                "client_open": self._client is not None,
                "has_pending_vop": self._pending_vop_response is not None,
            },
        )
        if self._client is None:
            raise FinTSOperationError("approve_vop", "client is not open")
        if self._pending_vop_response is None:
            raise FinTSOperationError("approve_vop", "no pending VOP challenge")

        try:
            with self._client_scope():
                logger.info("Approving pending payee verification challenge")
                result = self._client.approve_vop_response(self._pending_vop_response)
        except TanRequiredError as exc:
            self._pending_vop_response = None
            return (exc.challenge, None, None)
        except VOPRequiredError as exc:
            return (None, exc.challenge, None)
        except Exception as exc:
            logger.exception("Exception while approving VOP")
            if looks_like_tan_required(exc):
                self._pending_vop_response = None
                self._pending_tan_response = exc
                return (TanChallenge.from_response(exc), None, None)
            if looks_like_vop_required(exc):
                self._pending_vop_response = exc
                return (None, VOPChallenge.from_response(exc), None)
            raise FinTSOperationError("approve_vop", str(exc)) from exc

        if looks_like_tan_required(result):
            self._pending_vop_response = None
            self._pending_tan_response = result
            tan = TanChallenge.from_response(result)
            append_operation_step_log(
                "approve_vop",
                "tan_required",
                {"decoupled": tan.decoupled},
            )
            return (tan, None, None)
        if looks_like_vop_required(result):
            self._pending_vop_response = result
            vop = VOPChallenge.from_response(result)
            append_operation_step_log(
                "approve_vop",
                "vop_required",
                {"result": vop.result},
            )
            return (None, vop, None)

        self._pending_vop_response = None
        if getattr(self._client, "init_tan_response", None) is not None:
            self._client.init_tan_response = None
        try:
            result = self._finalize_pending_transfer_result(result)
        except TanRequiredError as exc:
            self._pending_tan_response = getattr(self._client, "init_tan_response", None) or self._pending_tan_response
            return (exc.challenge, None, None)
        except VOPRequiredError as exc:
            return (None, exc.challenge, None)
        append_operation_log(
            "approve_vop",
            {"status": "completed", "result_type": type(result).__name__},
        )
        return (None, None, result)
