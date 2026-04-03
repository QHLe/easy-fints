from __future__ import annotations

import os
import sys

from api_tan_test_helper import (
    build_config_payload,
    confirm_flow,
    load_dotenv_file,
    post_json,
    print_json,
    require_env,
)


def main() -> int:
    load_dotenv_file()

    base_url = "http://127.0.0.1:8000"
    payload = {
        "config": build_config_payload(),
        "source_account": require_env("FINTS_ACCOUNT_FILTER"),
        "account_name": require_env("FINTS_TRANSFER_ACCOUNT_NAME"),
        "recipient_name": require_env("FINTS_TRANSFER_RECIPIENT_NAME"),
        "recipient_iban": require_env("FINTS_TRANSFER_RECIPIENT_IBAN"),
        "amount": require_env("FINTS_TRANSFER_AMOUNT"),
        "purpose": require_env("FINTS_TRANSFER_PURPOSE"),
        "recipient_bic": os.getenv("FINTS_TRANSFER_RECIPIENT_BIC"),
        "endtoend_id": os.getenv("FINTS_TRANSFER_ENDTOEND_ID"),
        "instant_payment": os.getenv("FINTS_TRANSFER_INSTANT_PAYMENT"),
        "execution_date": os.getenv("FINTS_TRANSFER_EXECUTION_DATE"),
    }

    status, response_payload = post_json(
        f"{base_url.rstrip('/')}/transfer",
        payload,
    )

    if status == 200:
        print_json("Transfer response:", response_payload)
        return 0

    if status == 409 and response_payload.get("error") == "tan_required":
        print("TAN required for /transfer.")
        result = confirm_flow(base_url, response_payload, challenge_stem="api_transfer_challenge")
        print_json("Transfer response after confirmation:", result)
        return 0

    print_json(f"Unexpected response (status {status}):", response_payload)
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
