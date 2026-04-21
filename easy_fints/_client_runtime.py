"""Runtime and dialog/session handling for the FinTS client facade."""

from __future__ import annotations

import logging
from typing import Any, Iterator, Optional, Self

import fints.exceptions as fints_exceptions

from ._client_common import (
    augment_error_with_bank_response,
    looks_like_tan_required,
    looks_like_transfer_result,
    looks_like_vop_required,
)
from .exceptions import (
    FinTSCapabilityError,
    FinTSConfigError,
    FinTSOperationError,
    TanRequiredError,
    VOPRequiredError,
)
from .helpers import apply_tan_override, bootstrap_client, create_client, load_config, promote_two_step_tan
from .models import FinTSConfig, StoredBankInfo, StoredSepaProfile, TanChallenge, VOPChallenge


logger = logging.getLogger("pyfin_client")


class FinTSClientRuntimeMixin:
    @classmethod
    def from_env(
        cls,
        env_path: Optional[str] = None,
        overrides: Optional[dict[str, Any]] = None,
    ) -> Self:
        try:
            config = FinTSConfig(**load_config(env_path, overrides=overrides))
        except Exception as exc:
            raise FinTSConfigError("load_config", str(exc)) from exc
        return cls(config)

    @classmethod
    def from_profile(
        cls,
        bank_info: StoredBankInfo,
        *,
        user_id: str,
        pin: str,
        sepa_profile: Optional[StoredSepaProfile] = None,
        overrides: Optional[dict[str, Any]] = None,
    ) -> Self:
        if sepa_profile is not None:
            cfg = sepa_profile.to_client_config(
                bank_info,
                user_id=user_id,
                pin=pin,
                overrides=overrides,
            )
        else:
            cfg = {
                "bank": bank_info.bank_code,
                "user": user_id,
                "pin": pin,
                "server": bank_info.server,
                "product_id": bank_info.product_id,
            }
            if overrides:
                cfg.update({key: value for key, value in overrides.items() if value is not None})
        return cls(
            FinTSConfig(**cfg),
            profile_id=sepa_profile.profile_id if sepa_profile else None,
            display_name=sepa_profile.display_name if sepa_profile else None,
        )

    def __enter__(self) -> Self:
        if self._client is None:
            logger.info("Opening FinTS client: %s", self.config.to_safe_dict())
            self._client = create_client(self.config.to_client_config())
            self._prepare_client(self._client)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        if self._client is None:
            return
        try:
            logger.debug("Closing FinTS client")
            if self._has_standing_dialog():
                self._client.__exit__(None, None, None)
            elif hasattr(self._client, "close"):
                self._client.close()
        except Exception:
            pass
        finally:
            self._client = None
            self._pending_tan_response = None
            self._pending_vop_response = None
            self._clear_pending_transfer()

    def clear_pending_confirmations(self) -> None:
        """Drop local pending TAN/VoP state before retrying a transfer in the same client context."""
        self._pending_tan_response = None
        self._pending_vop_response = None
        self._clear_pending_transfer()
        if self._client is not None and getattr(self._client, "init_tan_response", None) is not None:
            self._client.init_tan_response = None

    def _remember_pending_transfer(
        self,
        params: dict[str, Any],
        *,
        transfer_overview: dict[str, Any] | None = None,
    ) -> None:
        self._pending_transfer_params = dict(params)
        self._pending_transfer_overview = dict(transfer_overview) if transfer_overview is not None else None

    def _clear_pending_transfer(self) -> None:
        self._pending_transfer_params = None
        self._pending_transfer_overview = None

    def _finalize_pending_transfer_result(self, result: Any) -> Any:
        if self._pending_transfer_params is None:
            return result
        if looks_like_transfer_result(result):
            response = self.transfer_response_from_result(
                result,
                self._pending_transfer_params,
                transfer_overview=self._pending_transfer_overview,
            )
            self._clear_pending_transfer()
            return response
        pending_params = dict(self._pending_transfer_params)
        self._clear_pending_transfer()
        return self.initiate_transfer(**pending_params)

    def _has_standing_dialog(self) -> bool:
        if self._client is None:
            return False
        return getattr(self._client, "_standing_dialog", None) is not None

    def _raise_if_initial_tan_required(self) -> None:
        if self._client is None:
            return
        init_tan_response = getattr(self._client, "init_tan_response", None)
        if not looks_like_tan_required(init_tan_response):
            return
        self._pending_tan_response = init_tan_response
        raise TanRequiredError("open_dialog", TanChallenge.from_response(init_tan_response))

    def _prepare_client(self, client: Any) -> Any:
        self._run(
            "bootstrap",
            bootstrap_client,
            client,
            tan_mechanism=self.config.tan_mechanism,
            tan_mechanism_before_bootstrap=bool(self.config.tan_mechanism_before_bootstrap),
        )
        self._run("promote_two_step_tan", promote_two_step_tan, client)
        if not self.config.tan_mechanism_before_bootstrap:
            self._run("apply_tan_override", apply_tan_override, client, self.config.tan_mechanism)
        return client

    def _ensure_client_prepared(self) -> Any:
        if self._client is None:
            logger.info("Opening FinTS client: %s", self.config.to_safe_dict())
            self._client = create_client(self.config.to_client_config())
            self._prepare_client(self._client)
        return self._client

    def _open_dialog_for_operation(self) -> Any:
        client = self._ensure_client_prepared()
        if self._has_standing_dialog():
            return client
        try:
            logger.debug("Opening FinTS dialog for operation")
            client.__enter__()
            self._raise_if_initial_tan_required()
            return client
        except TanRequiredError:
            raise
        except Exception as exc:
            logger.exception("Exception while opening FinTS dialog")
            try:
                if getattr(fints_exceptions, "FinTSClientPINError", None) and isinstance(
                    exc, fints_exceptions.FinTSClientPINError
                ):
                    raise FinTSOperationError(
                        "open_dialog",
                        augment_error_with_bank_response(
                            f"PIN rejected by bank or invalid PIN: {exc}"
                        ),
                    ) from exc
                if getattr(fints_exceptions, "FinTSDialogInitError", None) and isinstance(
                    exc, fints_exceptions.FinTSDialogInitError
                ):
                    raise FinTSOperationError(
                        "open_dialog",
                        augment_error_with_bank_response(
                            f"Dialog initialization failed: {exc}"
                        ),
                    ) from exc
            except FinTSOperationError:
                raise

            if looks_like_tan_required(exc):
                self._pending_tan_response = exc
                raise TanRequiredError("open_dialog", TanChallenge.from_response(exc)) from exc
            if looks_like_vop_required(exc):
                self._pending_vop_response = exc
                raise VOPRequiredError("open_dialog", VOPChallenge.from_response(exc)) from exc
            raise FinTSOperationError("open_dialog", str(exc)) from exc

    class _ClientScope:
        def __init__(self, owner: "FinTSClientRuntimeMixin"):
            self.owner = owner
            self.owned_client = False
            self.entered = False
            self.exit_performed = False
            self.preserve_client = False

        def __enter__(self) -> Any:
            self.owned_client = self.owner._client is None
            if self.owned_client:
                logger.debug("Creating owned client in _client_scope: %s", self.owner.config.to_safe_dict())
                self.owner._client = create_client(self.owner.config.to_client_config())
                self.owner._prepare_client(self.owner._client)

            if not self.owner._has_standing_dialog():
                try:
                    self.owner._open_dialog_for_operation()
                    self.entered = True
                except TanRequiredError:
                    self.preserve_client = True
                    logger.info("Preserving FinTS client after TAN required during dialog open")
                    raise
                except VOPRequiredError:
                    self.preserve_client = True
                    logger.info("Preserving FinTS client after VOP required during dialog open")
                    raise
                except Exception:
                    if self.owned_client:
                        self.owner.close()
                    raise
            return self.owner._client

        def __exit__(self, exc_type, exc, tb) -> bool:
            if isinstance(exc, TanRequiredError):
                self.preserve_client = True
                logger.info("Preserving FinTS client for pending TAN resume")
                return False
            if isinstance(exc, VOPRequiredError):
                self.preserve_client = True
                logger.info("Preserving FinTS client for pending VOP resume")
                return False

            if exc is not None and not isinstance(exc, FinTSOperationError):
                logger.exception("Exception while in client scope")
                if looks_like_tan_required(exc):
                    self.owner._pending_tan_response = exc
                    self.preserve_client = True
                    logger.info("Preserving FinTS client after TAN-required exception")
                    raise TanRequiredError("open_dialog", TanChallenge.from_response(exc)) from exc
                if looks_like_vop_required(exc):
                    self.owner._pending_vop_response = exc
                    self.preserve_client = True
                    logger.info("Preserving FinTS client after VOP-required exception")
                    raise VOPRequiredError("open_dialog", VOPChallenge.from_response(exc)) from exc

                try:
                    try:
                        if hasattr(self.owner._client, "pause_dialog"):
                            self.owner._client.pause_dialog()
                            logger.debug("Paused standing dialog to avoid commit (error path)")
                    except Exception:
                        logger.debug("pause_dialog() failed during error shutdown")

                    try:
                        self.owner._client.__exit__(type(exc), exc, exc.__traceback__)
                        self.exit_performed = True
                    except Exception:
                        logger.exception("Exception during __exit__ while handling error")
                except Exception:
                    logger.exception("Unexpected during error shutdown")
                raise FinTSOperationError("open_dialog", str(exc)) from exc

            if self.owned_client:
                if self.preserve_client:
                    logger.info("Keeping owned FinTS client alive for session resume")
                    return False
                if self.entered and not self.exit_performed:
                    try:
                        try:
                            if hasattr(self.owner._client, "pause_dialog"):
                                self.owner._client.pause_dialog()
                                logger.debug("Paused standing dialog during final cleanup")
                        except Exception:
                            logger.debug("pause_dialog() failed during final cleanup")
                        try:
                            self.owner._client.__exit__(None, None, None)
                        except Exception:
                            logger.exception("Exception during final __exit__ cleanup")
                    except Exception:
                        logger.exception("Unexpected during final cleanup")
                self.owner.close()
            return False

    def _client_scope(self) -> Iterator[Any]:
        return self._ClientScope(self)

    def _run(self, operation: str, func, *args, capability_context: Optional[str] = None, **kwargs):
        logger.info("Starting operation '%s'", operation)
        try:
            result = func(*args, **kwargs)
        except fints_exceptions.FinTSUnsupportedOperation as exc:
            logger.exception("Operation '%s' is not supported", operation)
            raise FinTSCapabilityError(
                operation,
                capability_context or "unsupported_operation",
                augment_error_with_bank_response(str(exc)),
            ) from exc
        except Exception as exc:
            logger.exception("Operation '%s' raised exception", operation)
            try:
                if getattr(fints_exceptions, "FinTSClientPINError", None) and isinstance(
                    exc, fints_exceptions.FinTSClientPINError
                ):
                    raise FinTSOperationError(
                        operation,
                        augment_error_with_bank_response(
                            f"PIN rejected by bank or invalid PIN: {exc}"
                        ),
                    ) from exc
                if getattr(fints_exceptions, "FinTSDialogInitError", None) and isinstance(
                    exc, fints_exceptions.FinTSDialogInitError
                ):
                    raise FinTSOperationError(
                        operation,
                        augment_error_with_bank_response(
                            f"Dialog initialization failed: {exc}"
                        ),
                    ) from exc
            except FinTSOperationError:
                raise

            if looks_like_tan_required(exc):
                self._pending_tan_response = exc
                raise TanRequiredError(operation, TanChallenge.from_response(exc)) from exc
            if looks_like_vop_required(exc):
                self._pending_vop_response = exc
                raise VOPRequiredError(operation, VOPChallenge.from_response(exc)) from exc

            raise FinTSOperationError(operation, str(exc)) from exc

        if looks_like_tan_required(result):
            logger.info("Operation '%s' requires TAN", operation)
            self._pending_tan_response = result
            raise TanRequiredError(operation, TanChallenge.from_response(result))
        if looks_like_vop_required(result):
            logger.info("Operation '%s' requires payee verification approval", operation)
            self._pending_vop_response = result
            raise VOPRequiredError(operation, VOPChallenge.from_response(result))

        logger.info("Operation '%s' completed with result_type=%s", operation, type(result).__name__)
        return result
