from __future__ import annotations

import base64
import json
import mimetypes
import os
from pathlib import Path
from typing import Any
from urllib import error, request

from src.env_config import resolve_env_file


ROOT = Path(__file__).resolve().parent
CHALLENGE_DIR = ROOT / "logs"


def load_dotenv_file(path: Path | None = None) -> None:
    env_path = path or resolve_env_file()
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip().strip("\"'")


def require_env(name: str) -> str:
    value = os.getenv(name)
    if value:
        return value
    raise RuntimeError(f"Missing required env var: {name}")


def build_config_payload() -> dict[str, Any]:
    payload = {
        "bank": require_env("FINTS_BLZ"),
        "user": require_env("FINTS_USER"),
        "pin": require_env("FINTS_PIN"),
        "server": require_env("FINTS_SERVER"),
    }
    customer_id = os.getenv("FINTS_CUSTOMER_ID")
    if customer_id:
        payload["customer_id"] = customer_id
    product_id = os.getenv("FINTS_PRODUCT_ID")
    if product_id:
        payload["product_id"] = product_id
    tan_mechanism = os.getenv("FINTS_TAN_MECHANISM")
    if tan_mechanism:
        payload["tan_mechanism"] = tan_mechanism
    tan_mechanism_before_bootstrap = os.getenv("FINTS_TAN_MECHANISM_BEFORE_BOOTSTRAP")
    if tan_mechanism_before_bootstrap:
        payload["tan_mechanism_before_bootstrap"] = tan_mechanism_before_bootstrap
    return payload


def post_json(url: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body) if body else {}
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        response_payload = json.loads(body) if body else {}
        return exc.code, response_payload


def challenge_extension(mime_type: str | None) -> str:
    if not mime_type:
        return ".bin"
    return mimetypes.guess_extension(mime_type) or ".bin"


def should_save_challenge_images() -> bool:
    return os.getenv("PYFIN_SAVE_CHALLENGE_IMAGES", "").strip().lower() in {"1", "true", "yes", "on"}


def save_challenge_image(challenge: dict[str, Any], stem: str) -> Path | None:
    if not should_save_challenge_images():
        return None
    image_base64 = challenge.get("image_base64")
    if not image_base64:
        return None
    mime_type = challenge.get("image_mime_type")
    image_path = CHALLENGE_DIR / f"{stem}{challenge_extension(mime_type)}"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(base64.b64decode(image_base64))
    return image_path


def print_json(title: str, payload: Any) -> None:
    print(title)
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def submit_tan_flow(base_url: str, response_payload: dict[str, Any], *, challenge_stem: str) -> dict[str, Any]:
    session_id = response_payload.get("session_id")
    challenge = response_payload.get("challenge") or {}
    if not session_id:
        raise RuntimeError("TAN response did not include session_id")

    print(f"Session ID: {session_id}")
    if challenge.get("message"):
        print(f"Challenge: {challenge['message']}")

    image_path = save_challenge_image(challenge, challenge_stem)
    if image_path is not None:
        print(f"Challenge image saved to: {image_path}")

    while True:
        tan = input("Enter TAN and press Enter (blank submits empty TAN): ").strip()
        status, payload = post_json(
            f"{base_url.rstrip('/')}/submit-tan",
            {"session_id": session_id, "tan": tan},
        )
        if status == 200:
            return payload
        if status != 409 or payload.get("error") != "tan_required":
            raise RuntimeError(f"submit-tan failed with status {status}: {json.dumps(payload)}")

        challenge = payload.get("challenge") or {}
        if challenge.get("message"):
            print(f"Next challenge: {challenge['message']}")
        image_path = save_challenge_image(challenge, challenge_stem)
        if image_path is not None:
            print(f"Updated challenge image saved to: {image_path}")
