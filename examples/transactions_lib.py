from __future__ import annotations

import os
import sys

from easy_fints import TanRequiredError

from lib_helper import build_fints, confirm_with_fints, load_dotenv_file, parse_optional_date_env, print_data


def main() -> int:
    load_dotenv_file()

    kwargs: dict[str, object] = {}
    date_from = parse_optional_date_env("FINTS_TX_DATE_FROM")
    date_to = parse_optional_date_env("FINTS_TX_DATE_TO")
    if date_from:
        kwargs["date_from"] = date_from
    if date_to:
        kwargs["date_to"] = date_to
    if not date_from:
        kwargs["days"] = int(os.getenv("FINTS_TX_DAYS", "30"))

    with build_fints() as fints:
        try:
            transactions = fints.transactions(**kwargs)
        except TanRequiredError as exc:
            print("TAN required for transactions().")
            transactions = confirm_with_fints(
                fints,
                exc,
                challenge_stem="lib_transactions_challenge",
                resume_action=lambda: fints.transactions(**kwargs),
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
