from __future__ import annotations

import sys

from easy_fints import TanRequiredError

from lib_helper import build_fints, confirm_with_fints, load_dotenv_file, print_data


def main() -> int:
    load_dotenv_file()

    with build_fints() as fints:
        try:
            balance = fints.account_overview(include_transaction_count_days=14)
        except TanRequiredError as exc:
            print("TAN required for account_overview().")
            balance = confirm_with_fints(
                fints,
                exc,
                challenge_stem="lib_balance_challenge",
                resume_action=lambda: fints.account_overview(include_transaction_count_days=14),
            )

    print_data("Balance response:", balance)
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
