from __future__ import annotations

import os
import sys
from api_tan_helper import build_config_payload, confirm_flow, load_dotenv_file, post_json, print_json


def main() -> int:
    load_dotenv_file()

    base_url = "http://127.0.0.1:8000"
    payload = {"config": build_config_payload()}
    date_from = os.getenv("FINTS_TX_DATE_FROM")
    date_to = os.getenv("FINTS_TX_DATE_TO")
    if date_from:
        payload["date_from"] = date_from
    if date_to:
        payload["date_to"] = date_to
    if not date_from:
        payload["days"] = int(os.getenv("FINTS_TX_DAYS", "30"))
    status, payload = post_json(
        f"{base_url.rstrip('/')}/transactions",
        payload,
    )

    if status == 200:
        print_json("Transactions response:", payload)
        return 0

    if status == 409 and payload.get("error") == "tan_required":
        print("TAN required for /transactions.")
        result = confirm_flow(base_url, payload, challenge_stem="api_transactions_challenge")
        print_json("Transactions response after confirmation:", result)
        return 0

    print_json(f"Unexpected response (status {status}):", payload)
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
