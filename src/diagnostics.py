"""Helpers for decoding recent FinTS exchange diagnostics from local logs."""

from __future__ import annotations

import base64
import re
from pathlib import Path


RAW_MESSAGES_LOG = Path("logs") / "raw_messages.log"
_RESPONSE_ENTRY_RE = re.compile(r"(?P<code>\d{4})::(?P<message>.*)")


def read_last_incoming_message_text(log_path: Path = RAW_MESSAGES_LOG) -> str | None:
    if not log_path.exists():
        return None

    lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    for index in range(len(lines) - 1, -1, -1):
        if lines[index].strip() != "INCOMING (base64):":
            continue
        if index + 1 >= len(lines):
            return None
        payload = lines[index + 1].strip()
        if not payload:
            return None
        try:
            decoded = base64.b64decode(payload)
        except Exception:
            return None
        return decoded.decode("iso-8859-1", errors="replace")
    return None


def extract_bank_response_entries(message_text: str) -> list[str]:
    entries: list[str] = []
    for segment in message_text.split("'"):
        if not segment.startswith(("HIRMG", "HIRMS")):
            continue
        parts = segment.split("+")[1:]
        for part in parts:
            match = _RESPONSE_ENTRY_RE.match(part)
            if not match:
                continue
            code = match.group("code")
            text = match.group("message").strip() or "(no text)"
            entries.append(f"{code} {text}")
    return entries


def summarize_last_bank_response(log_path: Path = RAW_MESSAGES_LOG) -> str | None:
    message_text = read_last_incoming_message_text(log_path=log_path)
    if not message_text:
        return None
    entries = extract_bank_response_entries(message_text)
    if not entries:
        return None
    return "; ".join(entries)
