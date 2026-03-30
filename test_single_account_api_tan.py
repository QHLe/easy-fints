from __future__ import annotations

import os
import sys

from api_tan_test_helper import (
    build_config_payload,
    load_dotenv_file,
    post_json,
    print_json,
    require_env,
    submit_tan_flow,
)


def main() -> int:
    load_dotenv_file()

    base_url = os.getenv("PYFIN_API_BASE_URL", "http://127.0.0.1:8000")
    account_filter = require_env("FINTS_ACCOUNT_FILTER")
    days = int(os.getenv("FINTS_TX_DAYS", "30"))
    tx_count_days = int(os.getenv("FINTS_BALANCE_TX_COUNT_DAYS", "14"))

    common_payload = {
        "config": build_config_payload(),
        "account_filter": account_filter,
    }

    balance_status, balance_payload = post_json(
        f"{base_url.rstrip('/')}/balance",
        {
            **common_payload,
            "include_transaction_count_days": tx_count_days,
        },
    )

    if balance_status == 200:
        print_json("Balance response:", balance_payload)
    elif balance_status == 409 and balance_payload.get("error") == "tan_required":
        print("TAN required for /balance.")
        result = submit_tan_flow(base_url, balance_payload, challenge_stem="api_single_balance_challenge")
        print_json("Balance response after TAN:", result)
    else:
        print_json(f"Unexpected balance response (status {balance_status}):", balance_payload)
        return 1

    transactions_status, transactions_payload = post_json(
        f"{base_url.rstrip('/')}/transactions",
        {
            **common_payload,
            "days": days,
        },
    )

    if transactions_status == 200:
        print_json("Transactions response:", transactions_payload)
        return 0

    if transactions_status == 409 and transactions_payload.get("error") == "tan_required":
        print("TAN required for /transactions.")
        result = submit_tan_flow(base_url, transactions_payload, challenge_stem="api_single_transactions_challenge")
        print_json("Transactions response after TAN:", result)
        return 0

    print_json(f"Unexpected transactions response (status {transactions_status}):", transactions_payload)
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
