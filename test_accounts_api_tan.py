from __future__ import annotations

import os
import sys
from api_tan_test_helper import build_config_payload, load_dotenv_file, post_json, print_json, submit_tan_flow


def main() -> int:
    load_dotenv_file()

    base_url = os.getenv("PYFIN_API_BASE_URL", "http://127.0.0.1:8000")
    status, payload = post_json(
        f"{base_url.rstrip('/')}/accounts",
        {"config": build_config_payload()},
    )

    if status == 200:
        print_json("Accounts response:", payload)
        return 0

    if status == 409 and payload.get("error") == "tan_required":
        print("TAN required for /accounts.")
        result = submit_tan_flow(base_url, payload, challenge_stem="api_accounts_challenge")
        print_json("Accounts response after TAN:", result)
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
