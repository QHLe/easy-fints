from __future__ import annotations

import os
import sys

from api_tan_helper import require_env

from easy_fints import lookup_bank_info

from lib_helper import load_dotenv_file, print_data


def main() -> int:
    load_dotenv_file()

    bank_info = lookup_bank_info(
        bank=require_env("FINTS_BLZ"),
        server=require_env("FINTS_SERVER"),
        product_id=require_env("FINTS_PRODUCT_ID"),
        product_name=os.getenv("FINTS_PRODUCT_NAME"),
        product_version=os.getenv("FINTS_PRODUCT_VERSION"),
    )

    print_data("Bank info response:", bank_info)
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
