"""Internal helpers so the integration package can be copied on its own."""

from __future__ import annotations

import base64
import datetime as dt
import json
import logging
import os
from pathlib import Path
from typing import Any, Iterable, Optional, Union

import dotenv
from fints.client import FinTS3PinTanClient, ING_BANK_IDENTIFIER, NeedTANResponse, NeedVOPResponse

from .env_config import load_project_env

load_project_env()

logger = logging.getLogger("pyfin_helpers")

CONFIG_ENV_VARS = {
    "product_id": ("FINTS_PRODUCT_ID",),
    "product_name": ("FINTS_PRODUCT_NAME",),
    "product_version": ("FINTS_PRODUCT_VERSION",),
    "tan_mechanism": ("FINTS_TAN_MECHANISM",),
    "tan_mechanism_before_bootstrap": ("FINTS_TAN_MECHANISM_BEFORE_BOOTSTRAP",),
}
_RUNTIME_PATCHES_APPLIED = False
SEPA_BASIC_ALLOWED_CHARS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 /-?:().,'+"
)
LOG_REDACTED = "[redacted]"
LOG_MASKED = "[masked]"
LOG_REDACT_KEYS = frozenset(
    {
        "pin",
        "tan",
        "image_base64",
        "challenge_html",
        "challenge_raw",
        "raw",
        "raw_repr",
    }
)
LOG_MASKED_NAME_KEYS = frozenset(
    {
        "account_name",
        "owner_name",
        "recipient_name",
        "counterparty_name",
        "close_match_name",
        "other_identification",
    }
)
LOG_IBAN_KEYS = frozenset(
    {
        "source_account",
        "source_account_label",
        "recipient_iban",
        "counterparty_iban",
        "iban",
        "account_label",
    }
)
LOG_TOKEN_MASK_KEYS = frozenset(
    {
        "user",
        "user_id",
        "customer_id",
        "account_number",
        "subaccount_number",
        "bank_identifier",
        "endtoend_id",
    }
)


def _first_present(*values: Any) -> Any:
    for value in values:
        # Avoid using `in` or equality comparisons with arbitrary objects
        # because their __eq__ may assume the other operand has attributes
        # (see mt940.Amount.__eq__ which accesses other.amount). Use
        # identity for None and explicit string check for empty string.
        if value is None:
            continue
        if isinstance(value, str) and value == "":
            continue
        return value
    return None


def _env_value(*names: str) -> Optional[str]:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def _field_names(env_names: Iterable[str]) -> str:
    return "/".join(env_names)


def _as_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def load_config(
    env_path: Optional[str] = None,
    overrides: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if env_path:
        dotenv.load_dotenv(env_path, override=True)

    logger.debug("Loading FINTS config from env_path=%s overrides=%s", env_path, bool(overrides))

    cfg = {
        name: _env_value(*env_names)
        for name, env_names in CONFIG_ENV_VARS.items()
    }

    if overrides:
        cfg.update({key: value for key, value in overrides.items() if value is not None})

    if "tan_mechanism_before_bootstrap" in cfg and cfg["tan_mechanism_before_bootstrap"] is not None:
        cfg["tan_mechanism_before_bootstrap"] = _as_bool(cfg["tan_mechanism_before_bootstrap"])

    # Only product_id is required when loading defaults from environment.
    if not cfg.get("product_id"):
        raise RuntimeError(
            "Missing FINTS config variable: " + _field_names(CONFIG_ENV_VARS["product_id"])
        )
    logger.debug("Loaded config keys: %s", ",".join(k for k, v in cfg.items() if v))
    return cfg


def apply_runtime_patches() -> None:
    """Apply idempotent runtime compatibility patches for python-fints."""
    global _RUNTIME_PATCHES_APPLIED
    if _RUNTIME_PATCHES_APPLIED or os.getenv("FINTS_DISABLE_LOCAL_PATCH") == "1":
        return

    if os.getenv("FINTS_DISABLE_CHALLENGE_PATCH") != "1":
        _patch_is_challenge_structured()
    if os.getenv("FINTS_DISABLE_BOOTSTRAP_PATCH") != "1":
        _patch_minimal_bootstrap()

    _patch_ing_two_step_tan()
    _patch_retry_detection()
    _patch_balance_conversions()
    _RUNTIME_PATCHES_APPLIED = True


def _patch_is_challenge_structured() -> None:
    original = FinTS3PinTanClient.is_challenge_structured

    def patched_is_challenge_structured(self: FinTS3PinTanClient) -> bool:
        mechanisms = self.get_tan_mechanisms() or {}
        current = self.get_current_tan_mechanism()
        if current not in mechanisms:
            return False
        return original(self)

    FinTS3PinTanClient.is_challenge_structured = patched_is_challenge_structured


def _patch_minimal_bootstrap() -> None:
    import fints.utils as fints_utils
    from fints.utils import minimal_interactive_cli_bootstrap as original_bootstrap

    def patched_bootstrap(client: Any) -> None:
        original_bootstrap(client)
        promote_two_step_tan(client, prefer_single_only=True)

    fints_utils.minimal_interactive_cli_bootstrap = patched_bootstrap


def _patch_balance_conversions() -> None:
    try:
        import fints.formals as fints_formals
    except Exception:
        return

    orig_b1 = getattr(fints_formals.Balance1, "as_mt940_Balance", None)
    orig_b2 = getattr(fints_formals.Balance2, "as_mt940_Balance", None)

    def _safe_balance1(self):
        from mt940.models import Balance

        try:
            amt = getattr(self, "amount", None)
            amt_str = None if amt is None else "{:.12f}".format(amt).rstrip("0")
            return Balance(
                self.credit_debit.value,
                amt_str,
                getattr(self, "date", None),
                currency=getattr(self, "currency", None),
            )
        except Exception:
            if orig_b1:
                return orig_b1(self)
            raise

    def _safe_balance2(self):
        from mt940.models import Balance

        try:
            amount_de = getattr(self, "amount", None)
            if amount_de is None:
                amt_str = None
                currency = None
            else:
                amt_val = getattr(amount_de, "amount", amount_de)
                amt_str = None if amt_val is None else "{:.12f}".format(amt_val).rstrip("0")
                currency = getattr(amount_de, "currency", None)
            return Balance(
                self.credit_debit.value,
                amt_str,
                getattr(self, "date", None),
                currency=currency,
            )
        except Exception:
            if orig_b2:
                return orig_b2(self)
            raise

    if orig_b1:
        fints_formals.Balance1.as_mt940_Balance = _safe_balance1
    if orig_b2:
        fints_formals.Balance2.as_mt940_Balance = _safe_balance2


def _select_two_step_tan_mechanism(
    client: Any,
    *,
    allowed_security_functions: Optional[Iterable[str]] = None,
) -> Optional[str]:
    methods = client.get_tan_mechanisms() or {}
    allowed = {str(item) for item in (allowed_security_functions or [])}
    for security_function, parameter in methods.items():
        code = str(security_function)
        if code == "999":
            continue
        if allowed and code not in allowed:
            continue
        if str(getattr(parameter, "tan_process", "")) != "2":
            continue
        try:
            client.set_tan_mechanism(str(getattr(parameter, "security_function", code)))
            return code
        except NotImplementedError:
            continue
    return None


def _apply_ing_two_step_tan_selection(client: Any, response: Any) -> bool:
    if getattr(response, "code", None) != "3920":
        return False
    if getattr(client, "bank_identifier", None) != ING_BANK_IDENTIFIER:
        return False

    allowed_security_functions = list(getattr(response, "parameters", []) or [])
    client.allowed_security_functions = allowed_security_functions
    current = getattr(client, "get_current_tan_mechanism", lambda: None)()
    if current is not None and str(current) in {str(item) for item in allowed_security_functions}:
        return False

    selected = _select_two_step_tan_mechanism(
        client,
        allowed_security_functions=allowed_security_functions,
    )
    if selected:
        logger.warning(
            "Enabled local ING two-step TAN patch and selected mechanism %s",
            selected,
        )
        return True

    logger.warning(
        "ING patch found no supported two-step TAN mechanism in %s; keeping current mechanism",
        allowed_security_functions,
    )
    return False


def _patch_ing_two_step_tan() -> None:
    original = FinTS3PinTanClient._process_response

    def patched_process_response(self: FinTS3PinTanClient, dialog: Any, segment: Any, response: Any):
        _apply_ing_two_step_tan_selection(self, response)
        return original(self, dialog, segment, response)

    FinTS3PinTanClient._process_response = patched_process_response


def _retry_response_from_raw_response(
    client: Any,
    command_seg: Any,
    response: Any,
    resume_func: Any,
    *,
    vop_standard: str | None = None,
) -> NeedTANResponse | NeedVOPResponse | None:
    hivpp = None
    if vop_standard:
        try:
            from fints.segments.auth import HIVPP1

            hivpp = response.find_segment_first(HIVPP1)
        except Exception:
            hivpp = None
        if hivpp is not None:
            vop_result = getattr(hivpp, "vop_single_result", None)
            vop_code = getattr(vop_result, "result", None)
            if vop_code in {"RVNA", "RVNM", "RVMC"}:
                logger.warning(
                    "Detected VoP retry response in raw payment response fallback for segment %s",
                    getattr(getattr(command_seg, "header", None), "type", None),
                )
                return NeedVOPResponse(
                    vop_result=hivpp,
                    command_seg=command_seg,
                    resume_method=resume_func,
                )

    try:
        hitan = response.find_segment_first("HITAN")
    except Exception:
        hitan = None

    if hitan is None:
        return None

    logger.warning(
        "Detected TAN challenge in raw response fallback for segment %s",
        getattr(getattr(command_seg, "header", None), "type", None),
    )
    return NeedTANResponse(
        command_seg,
        hitan,
        resume_func,
        client.is_challenge_structured() if hasattr(client, "is_challenge_structured") else False,
        False,
        hivpp,
    )


def _patch_retry_detection() -> None:
    def patched_send_with_possible_retry(self: FinTS3PinTanClient, dialog: Any, command_seg: Any, resume_func: Any):
        with dialog:
            if self._need_twostep_tan_for_segment(command_seg):
                tan_seg = self._get_tan_segment(command_seg, "4")

                response = dialog.send(command_seg, tan_seg)

                for resp in response.responses(tan_seg):
                    if resp.code in ("0030", "3955"):
                        return NeedTANResponse(
                            command_seg,
                            response.find_segment_first("HITAN"),
                            resume_func,
                            self.is_challenge_structured(),
                            resp.code == "3955",
                        )
                    if resp.code.startswith("9"):
                        raise Exception(f"Error response: {response!r}")
            else:
                response = dialog.send(command_seg)
                retry_response = _retry_response_from_raw_response(self, command_seg, response, resume_func)
                if retry_response is not None:
                    return retry_response

            return resume_func(command_seg, response)

    def patched_send_pay_with_possible_retry(self: FinTS3PinTanClient, dialog: Any, command_seg: Any, resume_func: Any):
        vop_seg = []
        vop_standard = self._find_vop_format_for_segment(command_seg)
        if vop_standard:
            from fints.segments.auth import HKVPP1, HIVPP1, PSRD1

            vop_seg = [HKVPP1(supported_reports=PSRD1(psrd=[vop_standard]))]
        else:
            HIVPP1 = None

        with dialog:
            if self._need_twostep_tan_for_segment(command_seg):
                tan_seg = self._get_tan_segment(command_seg, "4")
                segments = vop_seg + [command_seg, tan_seg]

                response = dialog.send(*segments)

                if vop_standard:
                    hivpp = response.find_segment_first(HIVPP1, throw=True)

                    vop_result = hivpp.vop_single_result
                    if vop_result.result in ("RVNA", "RVNM", "RVMC") or (
                        vop_result.result == "RCVC" and "3945" in [res.code for res in response.responses(tan_seg)]
                    ):
                        return NeedVOPResponse(
                            vop_result=hivpp,
                            command_seg=command_seg,
                            resume_method=resume_func,
                        )
                else:
                    hivpp = None

                for resp in response.responses(tan_seg):
                    if resp.code in ("0030", "3955"):
                        return NeedTANResponse(
                            command_seg,
                            response.find_segment_first("HITAN"),
                            resume_func,
                            self.is_challenge_structured(),
                            resp.code == "3955",
                            hivpp,
                        )
                    if resp.code.startswith("9"):
                        raise Exception(f"Error response: {response!r}")
            else:
                response = dialog.send(command_seg)
                retry_response = _retry_response_from_raw_response(
                    self,
                    command_seg,
                    response,
                    resume_func,
                    vop_standard=vop_standard,
                )
                if retry_response is not None:
                    return retry_response

            return resume_func(command_seg, response)

    FinTS3PinTanClient._send_with_possible_retry = patched_send_with_possible_retry
    FinTS3PinTanClient._send_pay_with_possible_retry = patched_send_pay_with_possible_retry


def create_client(cfg: dict[str, Any]) -> FinTS3PinTanClient:
    # bank identifier must be provided explicitly in cfg (API must supply it)
    bank_identifier = cfg.get("bank")
    if not bank_identifier:
        raise RuntimeError("Missing bank identifier: provide 'bank' in config")
    logger.info("Creating FinTS client for bank=%s server=%s", bank_identifier, cfg.get("server"))

    # Build optional constructor kwargs and validate product_version length.
    constructor_kwargs: dict[str, Any] = {}
    if cfg.get("product_id"):
        constructor_kwargs["product_id"] = cfg["product_id"]
    if cfg.get("product_version"):
        pv = str(cfg["product_version"])
        if len(pv) > 5:
            raise RuntimeError("Invalid FINTS product_version: max length is 5 characters")
        constructor_kwargs["product_version"] = pv

    # Use positional construction to match the behavior of download_sepa.py
    client = FinTS3PinTanClient(
        bank_identifier,
        cfg["user"],
        cfg["pin"],
        cfg["server"],
        **constructor_kwargs,
    )

    if cfg.get("product_name"):
        product_version = cfg.get("product_version") or getattr(client, "product_version", None)
        client.set_product(cfg["product_name"], product_version)

    logger.debug("FinTS client created for bank=%s product=%s", bank_identifier, cfg.get("product_id"))
    return client


def apply_tan_override(client: Any, tan_mechanism: Optional[str] = None) -> None:
    tan_override = tan_mechanism
    if not tan_override:
        return
    client.set_tan_mechanism(tan_override)
    logger.info("Forcing TAN mechanism to %s", tan_override)


def should_apply_tan_before_bootstrap(value: Any) -> bool:
    return _as_bool(value)


def promote_two_step_tan(client: Any, *, prefer_single_only: bool = False) -> None:
    methods = client.get_tan_mechanisms() or {}
    current = client.get_current_tan_mechanism()
    if current in methods or not methods:
        return

    two_step_codes = [code for code in methods if code != "999"]
    if prefer_single_only and len(two_step_codes) != 1:
        return

    for code in two_step_codes:
        client.set_tan_mechanism(code)
        logger.info("Switching to two-step TAN mechanism %s", code)
        return


def bootstrap_client(
    client: Any,
    *,
    tan_mechanism: Optional[str] = None,
    tan_mechanism_before_bootstrap: bool = False,
) -> Any:
    """Align integration client setup with the known-good python-fints bootstrap flow."""
    logger.info("Bootstrapping FinTS client")
    required_attrs = (
        "get_current_tan_mechanism",
        "fetch_tan_mechanisms",
        "get_tan_mechanisms",
    )
    if not all(hasattr(client, attr) for attr in required_attrs):
        return client

    if should_apply_tan_before_bootstrap(tan_mechanism_before_bootstrap):
        apply_tan_override(client, tan_mechanism)

    current = client.get_current_tan_mechanism()
    if not current:
        logger.debug("No current TAN mechanism, fetching mechanisms")
        client.fetch_tan_mechanisms()

    methods_map = client.get_tan_mechanisms() or {}
    current = client.get_current_tan_mechanism()
    if current not in methods_map:
        logger.info(
            "Bootstrap TAN mechanism not in advertised methods: current=%s known=%s",
            current,
            list(methods_map.keys()),
        )
        return client
    return client


def account_label(
    account: Any,
    *,
    owner_name: Optional[str] = None,
    product_name: Optional[str] = None,
) -> str:
    normalized_owner_name = str(owner_name).strip() if owner_name is not None else None
    normalized_product_name = str(product_name).strip() if product_name is not None else None
    iban = getattr(account, "iban", None)
    if normalized_owner_name and normalized_product_name:
        return f"{normalized_owner_name} - {normalized_product_name}"
    if normalized_owner_name:
        return normalized_owner_name
    if normalized_product_name:
        return normalized_product_name
    return (
        iban
        or getattr(account, "account", None)
        or repr(account)
    )


def account_matches(account: Any, needle: Optional[str]) -> bool:
    if not needle:
        return True
    candidates = {
        value
        for value in (
            getattr(account, "iban", None),
            getattr(account, "account", None),
            repr(account),
        )
        if value
    }
    return needle in candidates


def compact_iban(value: str) -> str:
    return "".join(str(value).split()).upper()


def is_valid_iban(value: str) -> bool:
    iban = compact_iban(value)
    if len(iban) < 15 or len(iban) > 34:
        return False
    if not iban[:2].isalpha() or not iban[2:4].isdigit() or not iban.isalnum():
        return False
    rearranged = iban[4:] + iban[:4]
    numeric = []
    for char in rearranged:
        if char.isdigit():
            numeric.append(char)
        elif char.isalpha():
            numeric.append(str(ord(char) - 55))
        else:
            return False
    try:
        return int("".join(numeric)) % 97 == 1
    except ValueError:
        return False


def first_unsupported_sepa_char(value: str) -> Optional[str]:
    for char in str(value):
        if char not in SEPA_BASIC_ALLOWED_CHARS:
            return char
    return None


def select_accounts(accounts: Iterable[Any], needle: Optional[str] = None) -> list[Any]:
    return [account for account in accounts if account_matches(account, needle)]


def list_accounts(client: FinTS3PinTanClient) -> list[Any]:
    return list(client.get_sepa_accounts() or [])


def translate_account_type(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    try:
        code = int(str(value).strip())
    except (TypeError, ValueError):
        return str(value).strip() or None

    if 1 <= code <= 9:
        return "Girokonto / Kontokorrentkonto"
    if 10 <= code <= 19:
        return "Sparkonto"
    if 20 <= code <= 29:
        return "Festgeldkonto"
    if 30 <= code <= 39:
        return "Wertpapierdepot"
    if 40 <= code <= 49:
        return "Kredit- / Darlehenskonto"
    if 50 <= code <= 59:
        return "Kreditkartenkonto"
    if 60 <= code <= 69:
        return "Fondsdepot"
    if 70 <= code <= 79:
        return "Bausparvertrag"
    if 80 <= code <= 89:
        return "Versicherungsvertrag"
    if 90 <= code <= 99:
        return "Sonstiges Konto"
    return f"Kontoart {code}"


def list_account_information(client: FinTS3PinTanClient) -> list[dict[str, Any]]:
    try:
        information = client.get_information() or {}
    except Exception:
        return []
    accounts = information.get("accounts")
    return accounts if isinstance(accounts, list) else []


def _account_bank_code(account: Any) -> Optional[str]:
    return (
        getattr(getattr(account, "bank_identifier", None), "bank_code", None)
        or getattr(account, "blz", None)
        or getattr(account, "bank_code", None)
    )


def _account_information_bank_code(account_information: dict[str, Any]) -> Optional[str]:
    return (
        getattr(account_information.get("bank_identifier"), "bank_code", None)
        or account_information.get("bank_code")
    )


def match_account_information(account: Any, account_information: Iterable[dict[str, Any]]) -> Optional[dict[str, Any]]:
    account_iban = getattr(account, "iban", None)
    if account_iban:
        normalized_account_iban = compact_iban(account_iban)
        for candidate in account_information:
            candidate_iban = candidate.get("iban")
            if candidate_iban and compact_iban(candidate_iban) == normalized_account_iban:
                return candidate

    account_number = (
        getattr(account, "accountnumber", None)
        or getattr(account, "account_number", None)
        or getattr(account, "account", None)
    )
    if not account_number:
        return None

    account_subaccount = getattr(account, "subaccount", None) or getattr(account, "subaccount_number", None)
    account_bank_code = _account_bank_code(account)

    for candidate in account_information:
        candidate_account_number = candidate.get("account_number")
        if candidate_account_number != account_number:
            continue

        candidate_bank_code = _account_information_bank_code(candidate)
        if account_bank_code and candidate_bank_code and candidate_bank_code != account_bank_code:
            continue

        candidate_subaccount = candidate.get("subaccount_number")
        if account_subaccount and candidate_subaccount and candidate_subaccount != account_subaccount:
            continue

        return candidate

    return None


def get_balance(client: FinTS3PinTanClient, account: Any) -> Any:
    try:
        return client.get_balance(account)
    except Exception:
        for attr in ("balance", "saldo", "available_balance", "booking_balance"):
            if hasattr(account, attr):
                return getattr(account, attr)
    return None


def transaction_start_date(days: int) -> dt.date:
    return dt.date.today() - dt.timedelta(days=days)


def _transaction_data(tx: Any) -> dict[str, Any]:
    data = getattr(tx, "__dict__", {}).get("data")
    return data if isinstance(data, dict) else {}


def normalize_amount(value: Any) -> tuple[Any, Any]:
    if value is None:
        return (None, None)
    amount = getattr(value, "amount", None)
    currency = getattr(value, "currency", None)
    if amount is not None:
        return (amount, currency)
    if isinstance(value, (tuple, list)) and value:
        amount = value[0]
        currency = value[1] if len(value) > 1 else None
        return (amount, currency)
    return (value, None)


def normalize_transaction(tx: Any) -> dict[str, Any]:
    data = _transaction_data(tx)

    booking_date = _first_present(
        getattr(tx, "booking_date", None),
        getattr(tx, "date", None),
        data.get("date"),
        data.get("entry_date"),
    )
    value_date = _first_present(
        getattr(tx, "value_date", None),
        getattr(tx, "booking_date", None),
        getattr(tx, "date", None),
        data.get("entry_date"),
        data.get("date"),
    )
    amount_value, amount_currency = normalize_amount(
        _first_present(
            getattr(tx, "amount", None),
            getattr(tx, "transaction_amount", None),
            getattr(tx, "value", None),
            data.get("amount"),
        )
    )

    return {
        "booking_date": booking_date,
        "value_date": value_date,
        "amount": amount_value,
        "currency": _first_present(
            getattr(tx, "currency", None),
            amount_currency,
            data.get("currency"),
        ),
        "counterparty_name": _first_present(
            getattr(tx, "counterparty_name", None),
            getattr(tx, "name", None),
            getattr(tx, "other_account_name", None),
            getattr(tx, "recipient_name", None),
            data.get("applicant_name"),
            data.get("recipient_name"),
        ),
        "counterparty_iban": _first_present(
            getattr(tx, "counterparty_iban", None),
            getattr(tx, "iban", None),
            getattr(tx, "account", None),
            getattr(tx, "other_account", None),
            data.get("applicant_iban"),
            data.get("recipient_iban"),
            data.get("applicant_bin"),
        ),
        "purpose": _first_present(
            getattr(tx, "usage", None),
            getattr(tx, "purpose", None),
            getattr(tx, "text", None),
            getattr(tx, "remittance_information", None),
            data.get("purpose"),
            data.get("additional_purpose"),
            data.get("posting_text"),
        ),
        "raw": repr(tx),
    }


def parse_fints_raw_messages_log_text(text: str) -> list[dict[str, Any]]:
    """Parse a FinTS raw_messages.log text into a JSON-serializable structure.

    The log uses entries separated by lines with "---" and contains a
    `TIME:` header plus `OUTGOING (base64):` and `INCOMING (base64):`
    sections. This function decodes base64 blocks and — when the
    `mt940` package is available — attempts to parse any embedded MT940
    statement segments into simple dicts.
    """
    import base64
    import re

    entries = re.split(r"^---\s*$", text, flags=re.M)
    parsed_entries: list[dict[str, Any]] = []

    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue

        out_blocks: list[dict[str, Any]] = []
        in_blocks: list[dict[str, Any]] = []

        # Extract TIME if present
        time_val = None
        m = re.search(r"TIME:\s*(\S+)", entry)
        if m:
            try:
                time_val = float(m.group(1))
            except Exception:
                time_val = m.group(1)

        # Walk lines to collect base64 blocks (robust against wrapped lines)
        lines = entry.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.upper().startswith("OUTGOING (BASE64):"):
                i += 1
                b64_lines: list[str] = []
                while i < len(lines):
                    nxt = lines[i].strip()
                    if not nxt:
                        break
                    # stop if a new label starts
                    if nxt.upper().endswith("(BASE64):") or nxt.upper().startswith("TIME:"):
                        break
                    if nxt.upper().startswith("INCOMING (BASE64):"):
                        break
                    b64_lines.append(nxt)
                    i += 1
                b64 = "".join(b64_lines)
                if b64:
                    try:
                        decoded = base64.b64decode(b64).decode("utf-8", errors="replace")
                    except Exception:
                        try:
                            decoded = base64.b64decode(b64)
                        except Exception:
                            decoded = ""
                    out_blocks.append({"base64": b64, "decoded": decoded})
                continue

            if line.upper().startswith("INCOMING (BASE64):"):
                i += 1
                b64_lines = []
                while i < len(lines):
                    nxt = lines[i].strip()
                    if not nxt:
                        break
                    if nxt.upper().endswith("(BASE64):") or nxt.upper().startswith("TIME:"):
                        break
                    if nxt.upper().startswith("OUTGOING (BASE64):"):
                        break
                    b64_lines.append(nxt)
                    i += 1
                b64 = "".join(b64_lines)
                if b64:
                    try:
                        decoded = base64.b64decode(b64).decode("utf-8", errors="replace")
                    except Exception:
                        try:
                            decoded = base64.b64decode(b64)
                        except Exception:
                            decoded = ""
                    in_blocks.append({"base64": b64, "decoded": decoded})
                continue

            i += 1

        entry_obj: dict[str, Any] = {"time": time_val, "outgoing": out_blocks, "incoming": in_blocks}

        # Try to locate and parse MT940 payloads inside decoded blocks when mt940 is available
        mt940_parsed: list[Any] = []
        try:
            import mt940  # type: ignore

            def _try_parse(decoded_text: str) -> None:
                # Heuristic: only try when typical MT940 tags appear
                if not decoded_text or (":20:" not in decoded_text and "MT940" not in decoded_text.upper()):
                    return
                try:
                    stmts = mt940.parse(decoded_text)
                except Exception:
                    return

                for stmt in stmts:
                    stmt_obj: dict[str, Any] = {}
                    # statement-level data (may be dict-like on some mt940 versions)
                    stmt_obj["data"] = getattr(stmt, "data", None) or {}
                    txs = []
                    for tx in getattr(stmt, "transactions", []) or []:
                        txd = {
                            "amount": getattr(tx, "amount", None),
                            "currency": getattr(tx, "currency", None),
                            "booking_date": getattr(tx, "booking_date", None),
                            "value_date": getattr(tx, "value_date", None),
                            "entry_date": getattr(tx, "entry_date", None),
                            "data": getattr(tx, "data", None),
                        }
                        txs.append(txd)
                    stmt_obj["transactions"] = txs
                    mt940_parsed.append(stmt_obj)

            for blk in out_blocks + in_blocks:
                decoded = blk.get("decoded")
                if isinstance(decoded, bytes):
                    try:
                        decoded = decoded.decode("utf-8", errors="replace")
                    except Exception:
                        decoded = str(decoded)
                _try_parse(decoded or "")
        except Exception:
            # mt940 not installed or parse failed — leave mt940_parsed empty
            mt940_parsed = []

        if mt940_parsed:
            entry_obj["mt940"] = mt940_parsed

        parsed_entries.append(entry_obj)

    return parsed_entries


def parse_fints_raw_messages_log_file(path: Union[str, os.PathLike]) -> list[dict[str, Any]]:
    """Read a `raw_messages.log`-style file and return parsed JSON data."""
    p = Path(path)
    text = p.read_text(encoding="utf-8", errors="replace")
    return parse_fints_raw_messages_log_text(text)


def append_operation_log(operation: str, payload: dict[str, Any]) -> Path:
    """Append a JSONL record for a high-level operation under `logs/`."""
    return append_operation_step_log(operation, "completed", payload)


def _mask_middle(value: Any, *, visible_start: int = 2, visible_end: int = 2) -> str:
    text = str(value or "")
    if not text:
        return text
    if len(text) <= visible_start + visible_end:
        return "*" * len(text)
    return f"{text[:visible_start]}{'*' * (len(text) - visible_start - visible_end)}{text[-visible_end:]}"


def _mask_iban_for_log(value: Any) -> str:
    iban = compact_iban(str(value or ""))
    if not iban:
        return iban
    if len(iban) <= 8:
        return _mask_middle(iban, visible_start=2, visible_end=2)
    return f"{iban[:4]}{'*' * (len(iban) - 8)}{iban[-4:]}"


def _sanitize_log_value(key: str, value: Any) -> Any:
    if isinstance(value, dict):
        return {sub_key: _sanitize_log_value(str(sub_key), sub_value) for sub_key, sub_value in value.items()}
    if isinstance(value, list):
        return [_sanitize_log_value(key, item) for item in value]
    if value is None:
        return None

    lowered = key.lower()
    if lowered in LOG_REDACT_KEYS or lowered.endswith("_raw") or lowered.endswith("_html"):
        return LOG_REDACTED
    if lowered in LOG_MASKED_NAME_KEYS:
        return LOG_MASKED
    if lowered in LOG_IBAN_KEYS or lowered.endswith("_iban"):
        return _mask_iban_for_log(value)
    if lowered in LOG_TOKEN_MASK_KEYS:
        return _mask_middle(value)
    return value


def sanitize_log_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: _sanitize_log_value(str(key), value) for key, value in payload.items()}


def append_operation_step_log(operation: str, stage: str, payload: dict[str, Any]) -> Path:
    """Append a step-level JSONL record for an operation under `logs/`."""
    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{operation}.log"
    record = {
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "operation": operation,
        "stage": stage,
        **sanitize_log_payload(payload),
    }
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False))
        fh.write("\n")
    return log_path
