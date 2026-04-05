"""High-level service facade for library consumers."""

from __future__ import annotations

import datetime as dt
from typing import Optional

from .client import FinTSClient
from .models import (
    AccountSummary,
    AccountTransactions,
    FinTSConfig,
    TanChallenge,
    TransferResponse,
    TransactionRecord,
    VOPChallenge,
)


class FinTS:
    """Convenience facade around ``FinTSClient`` for library use."""

    def __init__(
        self,
        *,
        product_id: str,
        bank: str,
        user: str,
        pin: str,
        server: str,
        product_name: Optional[str] = None,
        product_version: Optional[str] = None,
        tan_mechanism: Optional[str] = None,
        tan_mechanism_before_bootstrap: bool = False,
    ):
        self.config = FinTSConfig(
            product_id=product_id,
            bank=bank,
            user=user,
            pin=pin,
            server=server,
            product_name=product_name,
            product_version=product_version,
            tan_mechanism=tan_mechanism,
            tan_mechanism_before_bootstrap=tan_mechanism_before_bootstrap,
        )
        self._client = FinTSClient(self.config)

    def __enter__(self) -> "FinTS":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def accounts(self, account_filter: Optional[str] = None) -> list[AccountSummary]:
        return self._client.list_accounts(account_filter=account_filter)

    def account_overview(
        self,
        *,
        account_filter: Optional[str] = None,
        include_transaction_count_days: Optional[int] = None,
    ) -> list[AccountSummary]:
        return self._client.get_account_overview(
            account_filter=account_filter,
            include_transaction_count_days=include_transaction_count_days,
        )

    def transactions(
        self,
        *,
        account_filter: Optional[str] = None,
        days: int = 30,
        date_from: Optional[dt.date] = None,
        date_to: Optional[dt.date] = None,
    ) -> list[TransactionRecord]:
        return self._client.list_transactions(
            account_filter=account_filter,
            days=days,
            date_from=date_from,
            date_to=date_to,
        )

    def transactions_by_account(
        self,
        *,
        account_filter: Optional[str] = None,
        days: int = 30,
        date_from: Optional[dt.date] = None,
        date_to: Optional[dt.date] = None,
    ) -> list[AccountTransactions]:
        return self._client.list_transactions_by_account(
            account_filter=account_filter,
            days=days,
            date_from=date_from,
            date_to=date_to,
        )

    def transfer(
        self,
        *,
        source_account: str,
        account_name: str,
        recipient_name: str,
        recipient_iban: str,
        recipient_bic: Optional[str],
        amount: str,
        purpose: str,
        endtoend_id: Optional[str] = None,
        instant_payment: bool = False,
        execution_date: Optional[dt.date | str] = None,
    ) -> TransferResponse:
        return self._client.initiate_transfer(
            source_account=source_account,
            account_name=account_name,
            recipient_name=recipient_name,
            recipient_iban=recipient_iban,
            recipient_bic=recipient_bic,
            amount=amount,
            purpose=purpose,
            endtoend_id=endtoend_id,
            instant_payment=instant_payment,
            execution_date=execution_date,
        )

    def confirm_pending(self, tan: str = "") -> tuple[Optional[TanChallenge], Optional[VOPChallenge], object]:
        return self._client.confirm_pending(tan=tan)

    def approve_vop(self) -> tuple[Optional[TanChallenge], Optional[VOPChallenge], object]:
        return self._client.approve_vop()
