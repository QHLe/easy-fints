from __future__ import annotations

import os
import sys

from api_tan_helper import load_dotenv_file, post_json, print_json, require_env


def main() -> int:
    load_dotenv_file()

    base_url = "http://127.0.0.1:8000"
    status, payload = post_json(
        f"{base_url.rstrip('/')}/bank-info",
        {
            "config": {
                "bank": require_env("FINTS_BLZ"),
                "server": require_env("FINTS_SERVER"),
                "product_id": require_env("FINTS_PRODUCT_ID"),
                **({"product_name": os.getenv("FINTS_PRODUCT_NAME")} if os.getenv("FINTS_PRODUCT_NAME") else {}),
                **({"product_version": os.getenv("FINTS_PRODUCT_VERSION")} if os.getenv("FINTS_PRODUCT_VERSION") else {}),
            }
        },
    )

    if status == 200:
        print_json("Bank info response:", payload)
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
