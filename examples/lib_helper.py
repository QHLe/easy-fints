from __future__ import annotations

import datetime as dt
import json
import os
from typing import Any, Callable

from api_tan_helper import load_dotenv_file, print_json, require_env, save_challenge_image

from easy_fints import FinTS, TanRequiredError, VOPRequiredError


def _as_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def build_fints() -> FinTS:
    return FinTS(
        product_id=require_env("FINTS_PRODUCT_ID"),
        bank=require_env("FINTS_BLZ"),
        user=require_env("FINTS_USER"),
        pin=require_env("FINTS_PIN"),
        server=require_env("FINTS_SERVER"),
        product_name=os.getenv("FINTS_PRODUCT_NAME"),
        product_version=os.getenv("FINTS_PRODUCT_VERSION"),
        tan_mechanism=os.getenv("FINTS_TAN_MECHANISM"),
        tan_mechanism_before_bootstrap=_as_bool(os.getenv("FINTS_TAN_MECHANISM_BEFORE_BOOTSTRAP")),
    )


def build_transfer_kwargs() -> dict[str, Any]:
    return {
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


def parse_optional_date_env(name: str) -> dt.date | None:
    raw_value = os.getenv(name)
    if not raw_value:
        return None
    try:
        return dt.date.fromisoformat(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"Invalid date in {name}: expected YYYY-MM-DD") from exc


def to_json_value(value: Any) -> Any:
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return to_json_value(value.to_dict())
    if isinstance(value, list):
        return [to_json_value(item) for item in value]
    if isinstance(value, tuple):
        return [to_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: to_json_value(item) for key, item in value.items()}
    return value


def print_data(title: str, payload: Any) -> None:
    print_json(title, to_json_value(payload))


def _print_tan_challenge(challenge, *, challenge_stem: str) -> None:
    if challenge.message:
        print(f"Challenge: {challenge.message}")
    image_path = save_challenge_image(challenge.to_dict(), challenge_stem)
    if image_path is not None:
        print(f"Challenge image saved to: {image_path}")


def _print_vop_challenge(vop) -> None:
    if vop.message:
        print(f"Payee verification: {vop.message}")
    if vop.result:
        print(f"VoP result: {vop.result}")
    if vop.close_match_name:
        print(f"Close match name: {vop.close_match_name}")
    if vop.other_identification:
        print(f"Other identification: {vop.other_identification}")
    if vop.na_reason:
        print(f"VoP reason: {vop.na_reason}")


def confirm_with_fints(
    fints: FinTS,
    error: TanRequiredError | VOPRequiredError,
    *,
    challenge_stem: str,
    resume_action: Callable[[], Any] | None = None,
) -> Any:
    tan_challenge = error.challenge if isinstance(error, TanRequiredError) else None
    vop_challenge = error.challenge if isinstance(error, VOPRequiredError) else None

    while True:
        if tan_challenge is not None:
            _print_tan_challenge(tan_challenge, challenge_stem=challenge_stem)
            if tan_challenge.decoupled:
                input("Press Enter after confirming in your banking app: ")
                tan_value = ""
            else:
                tan_value = input("Enter TAN and press Enter (blank submits empty TAN): ").strip()

            tan_challenge, vop_challenge, result = fints.confirm_pending(tan=tan_value)
        elif vop_challenge is not None:
            _print_vop_challenge(vop_challenge)
            decision = input("Approve payee verification? [y/N]: ").strip().lower()
            if decision not in {"y", "yes"}:
                raise RuntimeError("Payee verification was not approved.")

            tan_challenge, vop_challenge, result = fints.approve_vop()
        else:
            raise RuntimeError("No pending confirmation state available.")

        if result is not None:
            if resume_action is not None:
                return resume_action()
            return result
        if tan_challenge is None and vop_challenge is None:
            raise RuntimeError("Confirmation flow ended without a result.")


def print_exception(exc: Exception) -> None:
    print(f"Error: {exc}")
    if isinstance(exc, (TanRequiredError, VOPRequiredError)):
        print(json.dumps(to_json_value({"operation": exc.operation}), indent=2, ensure_ascii=False))
