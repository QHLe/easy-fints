from __future__ import annotations

import sys

from fints_rest_wrapper import TanRequiredError, VOPRequiredError

from lib_helper import (
    build_fints,
    build_transfer_kwargs,
    confirm_with_fints,
    load_dotenv_file,
    print_data,
)


def main() -> int:
    load_dotenv_file()

    with build_fints() as fints:
        try:
            transfer = fints.transfer(**build_transfer_kwargs())
        except (TanRequiredError, VOPRequiredError) as exc:
            print("Confirmation required for transfer().")
            transfer = confirm_with_fints(fints, exc, challenge_stem="lib_transfer_challenge")

    print_data("Transfer response:", transfer)
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
