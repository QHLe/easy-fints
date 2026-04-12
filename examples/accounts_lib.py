from __future__ import annotations

import sys

from easy_fints import TanRequiredError

from lib_helper import build_fints, confirm_with_fints, load_dotenv_file, print_data


def main() -> int:
    load_dotenv_file()

    with build_fints() as fints:
        try:
            accounts = fints.accounts()
        except TanRequiredError as exc:
            print("TAN required for accounts().")
            accounts = confirm_with_fints(
                fints,
                exc,
                challenge_stem="lib_accounts_challenge",
                resume_action=fints.accounts,
            )

    print_data("Accounts response:", accounts)
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
