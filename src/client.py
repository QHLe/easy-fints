"""High-level client for embedding pyfin into another Python app."""

from __future__ import annotations

import logging
from typing import Any, Iterator, Optional

import fints.exceptions as fints_exceptions
from fints.client import NeedTANResponse

logger = logging.getLogger("pyfin_client")

from .helpers import (
    apply_runtime_patches,
    apply_tan_override,
    append_operation_log,
    append_operation_step_log,
    bootstrap_client,
    create_client,
    get_balance,
    list_accounts,
    load_config,
    normalize_transaction,
    promote_two_step_tan,
    select_accounts,
    transaction_start_date,
)

from .diagnostics import summarize_last_bank_response
from .exceptions import FinTSConfigError, FinTSOperationError, TanRequiredError
from .models import (
    AccountSummary,
    AccountTransactions,
    FinTSConfig,
    StoredBankInfo,
    StoredSepaProfile,
    TanChallenge,
    TanMethod,
    TanMethodsSnapshot,
    TransactionRecord,
    serialize_value,
)

apply_runtime_patches()


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


class PyFinIntegrationClient:
    """Backend-oriented wrapper that returns structured objects instead of printing."""

    def __init__(
        self,
        config: FinTSConfig,
        *,
        profile_id: Optional[str] = None,
        display_name: Optional[str] = None,
        bank_info_path: Optional[str] = None,
        sepa_profile_path: Optional[str] = None,
        auto_persist: bool = True,
    ):
        self.config = config
        self._client = None
        self._pending_tan_response = None
        self.profile_id = profile_id
        self.display_name = display_name
        self.bank_info_path = bank_info_path
        self.sepa_profile_path = sepa_profile_path
        self.auto_persist = auto_persist

    @classmethod
    def from_env(
        cls,
        env_path: Optional[str] = None,
        overrides: Optional[dict[str, Any]] = None,
    ) -> "PyFinIntegrationClient":
        try:
            config = FinTSConfig(**load_config(env_path, overrides=overrides))
        except Exception as exc:
            raise FinTSConfigError("load_config", str(exc)) from exc
        return cls(
            config,
        )   

    @classmethod
    def from_profile(
        cls,
        bank_info: StoredBankInfo,
        *,
        user_id: str,
        pin: str,
        customer_id: Optional[str] = None,
        sepa_profile: Optional[StoredSepaProfile] = None,
        overrides: Optional[dict[str, Any]] = None,
    ) -> "PyFinIntegrationClient":
        if sepa_profile is not None:
            cfg = sepa_profile.to_client_config(
                bank_info,
                user_id=user_id,
                pin=pin,
                customer_id=customer_id,
                overrides=overrides,
            )
        else:
            cfg = {
                "bank": bank_info.bank_code,
                "user": user_id,
                "pin": pin,
                "server": bank_info.server,
                "product_id": bank_info.product_id,
                "customer_id": customer_id,
            }
            if overrides:
                cfg.update({key: value for key, value in overrides.items() if value is not None})
        return cls(
            FinTSConfig(**cfg),
            profile_id=sepa_profile.profile_id if sepa_profile else None,
            display_name=sepa_profile.display_name if sepa_profile else None,
        )

    def __enter__(self) -> "PyFinIntegrationClient":
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
            logger.debug("Closing FinTS client for user=%s", getattr(self.config, "user", None))
            if self._has_standing_dialog():
                self._client.__exit__(None, None, None)
            elif hasattr(self._client, "close"):
                self._client.close()
        except Exception:
            pass
        finally:
            self._client = None
            self._pending_tan_response = None

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
            raise FinTSOperationError("open_dialog", str(exc)) from exc

    def begin_accounts(self, account_filter: Optional[str] = None) -> list[AccountSummary]:
        client = self._open_dialog_for_operation()
        append_operation_step_log(
            "accounts",
            "started",
            {"filter_applied": bool(account_filter)},
        )
        accounts = select_accounts(self._run("list_accounts", list_accounts, client), account_filter)
        summaries = [AccountSummary.from_account(account) for account in accounts]
        append_operation_log(
            "accounts",
            {
                "filter_applied": bool(account_filter),
                "account_count": len(summaries),
            },
        )
        return summaries

    def resume_accounts(self, account_filter: Optional[str] = None) -> list[AccountSummary]:
        if not self._has_standing_dialog():
            raise FinTSOperationError("resume_accounts", "FinTS dialog is no longer open")
        accounts = select_accounts(self._run("list_accounts", list_accounts, self._client), account_filter)
        return [AccountSummary.from_account(account) for account in accounts]

    class _ClientScope:
        def __init__(self, owner: "PyFinIntegrationClient"):
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

            if exc is not None and not isinstance(exc, FinTSOperationError):
                logger.exception("Exception while in client scope")
                if looks_like_tan_required(exc):
                    self.owner._pending_tan_response = exc
                    self.preserve_client = True
                    logger.info("Preserving FinTS client after TAN-required exception")
                    raise TanRequiredError("open_dialog", TanChallenge.from_response(exc)) from exc

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

    def _run(self, operation: str, func, *args, **kwargs):
        logger.info("Starting operation '%s'", operation)
        try:
            result = func(*args, **kwargs)
        except Exception as exc:
            logger.exception("Operation '%s' raised exception", operation)
            # map known python-fints exceptions to clearer integration errors
            try:
                if getattr(fints_exceptions, "FinTSClientPINError", None) and isinstance(
                    exc, fints_exceptions.FinTSClientPINError
                ):
                    # include original exception text for diagnostics
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

            raise FinTSOperationError(operation, str(exc)) from exc

        if looks_like_tan_required(result):
            logger.info("Operation '%s' requires TAN", operation)
            self._pending_tan_response = result
            raise TanRequiredError(operation, TanChallenge.from_response(result))

        logger.info("Operation '%s' completed", operation)
        return result

    def submit_tan(self, tan: str = "") -> Optional[TanChallenge]:
        append_operation_step_log(
            "submit_tan",
            "started",
            {
                "client_open": self._client is not None,
                "has_pending_tan": self._pending_tan_response is not None,
                "tan_provided": bool(tan),
            },
        )
        if self._client is None:
            append_operation_step_log(
                "submit_tan",
                "failed",
                {
                    "reason": "client is not open",
                    "bank_response": summarize_last_bank_response(),
                },
            )
            raise FinTSOperationError("submit_tan", "client is not open")
        if self._pending_tan_response is None:
            append_operation_step_log(
                "submit_tan",
                "failed",
                {
                    "reason": "no pending TAN challenge",
                    "bank_response": summarize_last_bank_response(),
                },
            )
            raise FinTSOperationError("submit_tan", "no pending TAN challenge")

        try:
            with self._client_scope():
                logger.info("Submitting TAN for pending challenge (masked)")
                result = self._client.send_tan(self._pending_tan_response, tan)
        except TanRequiredError as exc:
            append_operation_step_log(
                "submit_tan",
                "challenge_returned",
                {"message": exc.message},
            )
            self._pending_tan_response = getattr(self._client, "init_tan_response", None) or self._pending_tan_response
            return exc.challenge
        except Exception as exc:
            logger.exception("Exception while submitting TAN")
            append_operation_step_log(
                "submit_tan",
                "failed",
                {
                    "reason": str(exc),
                    "bank_response": summarize_last_bank_response(),
                },
            )
            if looks_like_tan_required(exc):
                self._pending_tan_response = exc
                return TanChallenge.from_response(exc)
            raise FinTSOperationError("submit_tan", str(exc)) from exc

        if looks_like_tan_required(result):
            self._pending_tan_response = result
            append_operation_step_log(
                "submit_tan",
                "challenge_returned",
                {"message": serialize_value(getattr(result, "challenge", None))},
            )
            return TanChallenge.from_response(result)

        self._pending_tan_response = None
        if getattr(self._client, "init_tan_response", None) is not None:
            self._client.init_tan_response = None
        append_operation_log(
            "submit_tan",
            {"status": "completed"},
        )
        return None

    def _get_transactions_rows(self, client: Any, account: Any, days: int) -> list[dict[str, Any]]:
        start_date = transaction_start_date(days)
        raw_transactions = self._run(
            "get_transactions",
            client.get_transactions,
            account,
            start_date=start_date,
        ) or []
        return [normalize_transaction(transaction) for transaction in raw_transactions]

    def list_accounts(self, account_filter: Optional[str] = None) -> list[AccountSummary]:
        with self._client_scope() as client:
            accounts = select_accounts(self._run("list_accounts", list_accounts, client), account_filter)
            summaries = [AccountSummary.from_account(account) for account in accounts]
            return summaries

    def get_account_overview(
        self,
        *,
        account_filter: Optional[str] = None,
        include_transaction_count_days: Optional[int] = None,
    ) -> list[AccountSummary]:
        with self._client_scope() as client:
            append_operation_step_log(
                "balance",
                "started",
                {
                    "filter_applied": bool(account_filter),
                    "include_transaction_count_days": include_transaction_count_days,
                },
            )
            accounts = select_accounts(self._run("list_accounts", list_accounts, client), account_filter)
            overview = []
            for index, account in enumerate(accounts, start=1):
                account_summary = AccountSummary.from_account(account)
                append_operation_step_log(
                    "balance",
                    "account_started",
                    {
                        "account_index": index,
                    },
                )
                balance = self._run("get_balance", get_balance, client, account)
                transaction_count = None
                if include_transaction_count_days is not None:
                    rows = self._get_transactions_rows(client, account, include_transaction_count_days)
                    transaction_count = len(rows)
                result_item = AccountSummary.from_account(
                    account,
                    balance=balance,
                    transaction_count=transaction_count,
                )
                overview.append(result_item)
                append_operation_step_log(
                    "balance",
                    "account_completed",
                    {
                        "account_index": index,
                        "has_balance": result_item.balance is not None,
                        "transaction_count": result_item.transaction_count,
                    },
                )
            append_operation_log(
                "balance",
                {
                    "filter_applied": bool(account_filter),
                    "include_transaction_count_days": include_transaction_count_days,
                    "account_count": len(overview),
                },
            )
            return overview

    def list_transactions(
        self,
        *,
        account_filter: Optional[str] = None,
        days: int = 30,
    ) -> list[TransactionRecord]:
        records = []
        for bundle in self.list_transactions_by_account(account_filter=account_filter, days=days):
            records.extend(bundle.transactions)
        return records

    def list_transactions_by_account(
        self,
        *,
        account_filter: Optional[str] = None,
        days: int = 30,
    ) -> list[AccountTransactions]:
        with self._client_scope() as client:
            append_operation_step_log(
                "transactions",
                "started",
                {
                    "filter_applied": bool(account_filter),
                    "days": days,
                },
            )
            accounts = select_accounts(self._run("list_accounts", list_accounts, client), account_filter)
            bundles = []
            for index, account in enumerate(accounts, start=1):
                label = AccountSummary.from_account(account)
                append_operation_step_log(
                    "transactions",
                    "account_started",
                    {
                        "account_index": index,
                    },
                )
                rows = self._get_transactions_rows(client, account, days)
                transactions = [
                    TransactionRecord.from_row(label.label, index, row)
                    for index, row in enumerate(rows, start=1)
                ]
                bundle = AccountTransactions(
                    account=AccountSummary.from_account(
                        account,
                        transaction_count=len(transactions),
                    ),
                    transactions=transactions,
                )
                bundles.append(bundle)
                append_operation_step_log(
                    "transactions",
                    "account_completed",
                    {
                        "account_index": index,
                        "transaction_count": len(bundle.transactions),
                    },
                )
            append_operation_log(
                "transactions",
                {
                    "filter_applied": bool(account_filter),
                    "days": days,
                    "account_count": len(bundles),
                    "transaction_count": sum(len(bundle.transactions) for bundle in bundles),
                },
            )
            return bundles

    # Exporting transactions removed — use `list_transactions_by_account` instead.

    def get_tan_methods(self) -> TanMethodsSnapshot:
        with self._client_scope() as client:
            try:
                self._run("fetch_tan_mechanisms", client.fetch_tan_mechanisms)
            except FinTSOperationError as exc:
                # Some python-fints versions refuse this call once a dialog is already open.
                if "standing dialog" not in exc.message:
                    raise

            raw_methods = self._run("get_tan_mechanisms", client.get_tan_mechanisms) or {}
            current = self._run("get_current_tan_mechanism", client.get_current_tan_mechanism)
            current_name = None
            methods = []
            for code, method in raw_methods.items() if hasattr(raw_methods, "items") else []:
                methods.append(
                    TanMethod(
                        code=str(code),
                        name=serialize_value(getattr(method, "name", None)),
                        security_function=serialize_value(getattr(method, "security_function", None)),
                        identifier=serialize_value(getattr(method, "identifier", None)),
                    )
                )
                if str(code) == str(current):
                    current_name = serialize_value(getattr(method, "name", None))

            try:
                media = self._run("get_tan_media", client.get_tan_media)
            except FinTSOperationError:
                media = None

            snapshot = TanMethodsSnapshot(
                current=serialize_value(current),
                current_name=current_name,
                methods=methods,
                media=serialize_value(media),
            )
            return snapshot
