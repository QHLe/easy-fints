from __future__ import annotations

import sys
from api_tan_test_helper import build_config_payload, confirm_flow, load_dotenv_file, post_json, print_json


def main() -> int:
    load_dotenv_file()

    base_url = "http://127.0.0.1:8000"
    status, payload = post_json(
        f"{base_url.rstrip('/')}/balance",
        {"config": build_config_payload(), "include_transaction_count_days": 14},
    )

    if status == 200:
        print_json("Balance response:", payload)
        return 0

    if status == 409 and payload.get("error") == "tan_required":
        print("TAN required for /balance.")
        result = confirm_flow(base_url, payload, challenge_stem="api_balance_challenge")
        print_json("Balance response after confirmation:", result)
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
