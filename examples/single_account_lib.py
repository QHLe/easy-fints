from __future__ import annotations

import os
import sys

from easy_fints import TanRequiredError

from lib_helper import (
    build_fints,
    confirm_with_fints,
    load_dotenv_file,
    parse_optional_date_env,
    print_data,
    require_env,
)


def main() -> int:
    load_dotenv_file()

    account_filter = require_env("FINTS_ACCOUNT_FILTER")
    days = int(os.getenv("FINTS_TX_DAYS", "30"))
    date_from = parse_optional_date_env("FINTS_TX_DATE_FROM")
    date_to = parse_optional_date_env("FINTS_TX_DATE_TO")
    tx_count_days = int(os.getenv("FINTS_BALANCE_TX_COUNT_DAYS", "14"))

    with build_fints() as fints:
        try:
            balance = fints.account_overview(
                account_filter=account_filter,
                include_transaction_count_days=tx_count_days,
            )
        except TanRequiredError as exc:
            print("TAN required for account_overview().")
            balance = confirm_with_fints(
                fints,
                exc,
                challenge_stem="lib_single_balance_challenge",
                resume_action=lambda: fints.account_overview(
                    account_filter=account_filter,
                    include_transaction_count_days=tx_count_days,
                ),
            )

        print_data("Balance response:", balance)

        transaction_kwargs: dict[str, object] = {
            "account_filter": account_filter,
        }
        if date_from:
            transaction_kwargs["date_from"] = date_from
        if date_to:
            transaction_kwargs["date_to"] = date_to
        if not date_from:
            transaction_kwargs["days"] = days

        try:
            transactions = fints.transactions(**transaction_kwargs)
        except TanRequiredError as exc:
            print("TAN required for transactions().")
            transactions = confirm_with_fints(
                fints,
                exc,
                challenge_stem="lib_single_transactions_challenge",
                resume_action=lambda: fints.transactions(**transaction_kwargs),
            )

    print_data("Transactions response:", transactions)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
