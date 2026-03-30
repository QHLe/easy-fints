"""Shared environment-file loading helpers."""

from __future__ import annotations

import os
from pathlib import Path

import dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def resolve_env_file(default_name: str = ".env") -> Path:
    configured = os.getenv("FINTS_ENV_FILE")
    if configured:
        candidate = Path(configured)
        if not candidate.is_absolute():
            candidate = PROJECT_ROOT / candidate
        return candidate
    return PROJECT_ROOT / default_name


def load_project_env(default_name: str = ".env") -> Path:
    env_path = resolve_env_file(default_name=default_name)
    dotenv.load_dotenv(env_path, override=True)
    return env_path
