"""Read-side account, balance, and transaction flows for the FinTS client facade."""

from __future__ import annotations

import datetime as dt
from typing import Any, Optional

from .exceptions import FinTSOperationError
from .helpers import (
    account_label,
    append_debug_step_log,
    append_operation_log,
    append_operation_step_log,
    fints_debug_enabled,
    fints_debug_fail_only,
    fints_debug_level,
    get_balance,
    list_account_information,
    list_accounts,
    match_account_information,
    normalize_transaction,
    select_accounts,
    should_emit_debug,
    transaction_debug_failure_reasons,
    transaction_start_date,
)
from .models import AccountSummary, AccountTransactions, TanMethod, TanMethodsSnapshot, TransactionRecord, serialize_value


class FinTSClientReadMixin:
    def begin_accounts(self, account_filter: Optional[str] = None) -> list[AccountSummary]:
        client = self._open_dialog_for_operation()
        append_operation_step_log(
            "accounts",
            "started",
            {"filter_applied": bool(account_filter)},
        )
        accounts = select_accounts(self._run("list_accounts", list_accounts, client), account_filter)
        account_information = self._run("list_account_information", list_account_information, client)
        summaries = [self._account_summary(account, account_information) for account in accounts]
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
        account_information = self._run("list_account_information", list_account_information, self._client)
        return [self._account_summary(account, account_information) for account in accounts]

    def _normalize_transaction_rows(
        self,
        raw_transactions: list[Any],
        *,
        account: Any,
        start_date: dt.date,
        end_date: Optional[dt.date] = None,
    ) -> list[dict[str, Any]]:
        include_debug = fints_debug_enabled("mapping")
        rows = [normalize_transaction(transaction, include_debug=include_debug) for transaction in raw_transactions]
        self._append_transaction_debug_logs(
            account=account,
            start_date=start_date,
            end_date=end_date,
            rows=rows,
        )
        for row in rows:
            row.pop("__debug__", None)
        return rows

    def _append_transaction_debug_logs(
        self,
        *,
        account: Any,
        start_date: dt.date,
        end_date: Optional[dt.date],
        rows: list[dict[str, Any]],
    ) -> None:
        if not fints_debug_enabled("summary"):
            return

        account_label_value = account_label(account)
        failed_rows: list[tuple[int, dict[str, Any], dict[str, Any], list[str]]] = []
        for index, row in enumerate(rows, start=1):
            debug_info = row.get("__debug__") if isinstance(row.get("__debug__"), dict) else {}
            failure_reasons = list(debug_info.get("failure_reasons") or transaction_debug_failure_reasons(row))
            if failure_reasons:
                failed_rows.append((index, row, debug_info, failure_reasons))

        batch_failed = bool(failed_rows)
        if should_emit_debug("summary", failed=batch_failed):
            append_debug_step_log(
                "transactions",
                "summary",
                {
                    "debug_level": fints_debug_level(),
                    "fail_only": fints_debug_fail_only(),
                    "account_label": account_label_value,
                    "requested_start_date": serialize_value(start_date),
                    "requested_end_date": serialize_value(end_date),
                    "transaction_count": len(rows),
                    "failed_record_count": len(failed_rows),
                    "failed_record_indexes": [index for index, _, _, _ in failed_rows],
                },
            )

        if fints_debug_enabled("mapping"):
            for index, row in enumerate(rows, start=1):
                debug_info = row.get("__debug__") if isinstance(row.get("__debug__"), dict) else {}
                failure_reasons = list(debug_info.get("failure_reasons") or transaction_debug_failure_reasons(row))
                row_failed = bool(failure_reasons)
                if not should_emit_debug("mapping", failed=row_failed):
                    continue
                append_debug_step_log(
                    "transactions",
                    "mapping",
                    {
                        "debug_level": fints_debug_level(),
                        "fail_only": fints_debug_fail_only(),
                        "account_label": account_label_value,
                        "record_index": index,
                        "failed": row_failed,
                        "failure_reasons": failure_reasons,
                        "requested_start_date": serialize_value(start_date),
                        "requested_end_date": serialize_value(end_date),
                        "normalized": {
                            "booking_date": row.get("booking_date"),
                            "value_date": row.get("value_date"),
                            "amount": row.get("amount"),
                            "currency": row.get("currency"),
                            "counterparty_name": row.get("counterparty_name"),
                            "counterparty_iban": row.get("counterparty_iban"),
                            "purpose": row.get("purpose"),
                        },
                        "selected_sources": debug_info.get("sources"),
                        "mapping_modules": debug_info.get("applied_modules"),
                        "raw_type": debug_info.get("raw_type"),
                        "raw_keys": debug_info.get("raw_keys"),
                        "credit_debit_indicator": debug_info.get("credit_debit_indicator"),
                    },
                )

        if fints_debug_enabled("record_raw"):
            for index, row in enumerate(rows, start=1):
                debug_info = row.get("__debug__") if isinstance(row.get("__debug__"), dict) else {}
                failure_reasons = list(debug_info.get("failure_reasons") or transaction_debug_failure_reasons(row))
                row_failed = bool(failure_reasons)
                if not should_emit_debug("record_raw", failed=row_failed):
                    continue
                append_debug_step_log(
                    "transactions",
                    "record_raw",
                    {
                        "debug_level": fints_debug_level(),
                        "fail_only": fints_debug_fail_only(),
                        "account_label": account_label_value,
                        "record_index": index,
                        "failed": row_failed,
                        "failure_reasons": failure_reasons,
                        "raw_data": debug_info.get("raw_data"),
                        "raw_repr": row.get("raw"),
                    },
                )

    def _get_transactions_rows(self, client: Any, account: Any, days: int) -> list[dict[str, Any]]:
        start_date = transaction_start_date(days)
        raw_transactions = self._run(
            "get_transactions",
            client.get_transactions,
            account,
            start_date=start_date,
        ) or []
        return self._normalize_transaction_rows(
            raw_transactions,
            account=account,
            start_date=start_date,
        )

    def _get_transactions_rows_for_window(
        self,
        client: Any,
        account: Any,
        *,
        date_from: Optional[dt.date] = None,
        date_to: Optional[dt.date] = None,
        days: int = 30,
    ) -> list[dict[str, Any]]:
        start_date = date_from if date_from is not None else transaction_start_date(days)
        raw_transactions = self._run(
            "get_transactions",
            client.get_transactions,
            account,
            start_date=start_date,
            end_date=date_to,
        ) or []
        return self._normalize_transaction_rows(
            raw_transactions,
            account=account,
            start_date=start_date,
            end_date=date_to,
        )

    def _account_summary(
        self,
        account: Any,
        account_information: list[dict[str, Any]],
        *,
        balance: Any = None,
        transaction_count: Optional[int] = None,
    ) -> AccountSummary:
        return AccountSummary.from_account(
            account,
            account_info=match_account_information(account, account_information),
            balance=balance,
            transaction_count=transaction_count,
        )

    def list_accounts(self, account_filter: Optional[str] = None) -> list[AccountSummary]:
        with self._client_scope() as client:
            accounts = select_accounts(self._run("list_accounts", list_accounts, client), account_filter)
            account_information = self._run("list_account_information", list_account_information, client)
            summaries = [self._account_summary(account, account_information) for account in accounts]
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
            account_information = self._run("list_account_information", list_account_information, client)
            overview = []
            for index, account in enumerate(accounts, start=1):
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
                result_item = self._account_summary(
                    account,
                    account_information,
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
        date_from: Optional[dt.date] = None,
        date_to: Optional[dt.date] = None,
    ) -> list[TransactionRecord]:
        records = []
        for bundle in self.list_transactions_by_account(
            account_filter=account_filter,
            days=days,
            date_from=date_from,
            date_to=date_to,
        ):
            records.extend(bundle.transactions)
        return records

    def list_transactions_by_account(
        self,
        *,
        account_filter: Optional[str] = None,
        days: int = 30,
        date_from: Optional[dt.date] = None,
        date_to: Optional[dt.date] = None,
    ) -> list[AccountTransactions]:
        with self._client_scope() as client:
            append_operation_step_log(
                "transactions",
                "started",
                {
                    "filter_applied": bool(account_filter),
                    "days": days,
                    "date_from": serialize_value(date_from),
                    "date_to": serialize_value(date_to),
                },
            )
            accounts = select_accounts(self._run("list_accounts", list_accounts, client), account_filter)
            account_information = self._run("list_account_information", list_account_information, client)
            bundles = []
            for index, account in enumerate(accounts, start=1):
                label = self._account_summary(account, account_information)
                append_operation_step_log(
                    "transactions",
                    "account_started",
                    {
                        "account_index": index,
                    },
                )
                rows = self._get_transactions_rows_for_window(
                    client,
                    account,
                    days=days,
                    date_from=date_from,
                    date_to=date_to,
                )
                transactions = [
                    TransactionRecord.from_row(label.label, index, row)
                    for index, row in enumerate(rows, start=1)
                ]
                bundle = AccountTransactions(
                    account=self._account_summary(
                        account,
                        account_information,
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
                    "date_from": serialize_value(date_from),
                    "date_to": serialize_value(date_to),
                    "account_count": len(bundles),
                    "transaction_count": sum(len(bundle.transactions) for bundle in bundles),
                },
            )
            return bundles

    def get_tan_methods(self) -> TanMethodsSnapshot:
        with self._client_scope() as client:
            try:
                self._run("fetch_tan_mechanisms", client.fetch_tan_mechanisms)
            except FinTSOperationError as exc:
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

            return TanMethodsSnapshot(
                current=serialize_value(current),
                current_name=current_name,
                methods=methods,
                media=serialize_value(media),
            )
