"""Command-line helpers for running the REST server."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from .env_config import load_project_env


DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8000
DEFAULT_PID_FILE = ".fints-rest-server.pid"
DEFAULT_LOG_FILE = ".fints-rest-server.log"
STARTUP_WAIT_SECONDS = 0.75
STOP_WAIT_SECONDS = 5.0


def _read_pid(pid_file: Path) -> int | None:
    if not pid_file.exists():
        return None
    try:
        return int(pid_file.read_text(encoding="utf-8").strip())
    except (TypeError, ValueError):
        return None


def _process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _remove_pid_file(pid_file: Path) -> None:
    try:
        pid_file.unlink()
    except FileNotFoundError:
        pass


def _resolve_start_options(args: argparse.Namespace) -> tuple[str, int, Path, Path]:
    host = args.host or os.getenv("FINTS_SERVER_HOST", DEFAULT_HOST)
    port = args.port
    if port is None:
        port = int(os.getenv("FINTS_SERVER_PORT", str(DEFAULT_PORT)))
    pid_file = Path(args.pid_file or os.getenv("FINTS_SERVER_PID_FILE", DEFAULT_PID_FILE)).expanduser()
    log_file = Path(args.log_file or os.getenv("FINTS_SERVER_LOG_FILE", DEFAULT_LOG_FILE)).expanduser()
    return host, int(port), pid_file, log_file


def _resolve_pid_file(value: str | Path | None) -> Path:
    configured = value or os.getenv("FINTS_SERVER_PID_FILE", DEFAULT_PID_FILE)
    return Path(configured).expanduser()


def _start_server(args: argparse.Namespace) -> int:
    if args.env_file:
        os.environ["FINTS_ENV_FILE"] = str(args.env_file)
    load_project_env()
    host, port, pid_file, log_file = _resolve_start_options(args)

    existing_pid = _read_pid(pid_file)
    if existing_pid and _process_exists(existing_pid):
        print(f"Server already running with PID {existing_pid}.", file=sys.stderr)
        return 1
    if pid_file.exists():
        _remove_pid_file(pid_file)

    log_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.parent.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "easy_fints.fastapi_app:app",
        "--host",
        host,
        "--port",
        str(port),
    ]

    with log_file.open("ab") as log_handle:
        process = subprocess.Popen(
            command,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )

    time.sleep(STARTUP_WAIT_SECONDS)
    if process.poll() is not None:
        print(
            f"Server failed to start. See log file: {log_file}",
            file=sys.stderr,
        )
        return process.returncode or 1

    pid_file.write_text(f"{process.pid}\n", encoding="utf-8")
    print(
        f"Started fints-rest-server on {host}:{port} with PID {process.pid}. "
        f"Log: {log_file}"
    )
    return 0


def _stop_server(args: argparse.Namespace) -> int:
    pid_file = _resolve_pid_file(args.pid_file)
    pid = _read_pid(pid_file)
    if pid is None:
        if pid_file.exists():
            _remove_pid_file(pid_file)
        print(f"No running server found. Missing or invalid PID file: {pid_file}", file=sys.stderr)
        return 1

    if not _process_exists(pid):
        _remove_pid_file(pid_file)
        print(f"Removed stale PID file for process {pid}.")
        return 0

    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + STOP_WAIT_SECONDS
    while time.monotonic() < deadline:
        if not _process_exists(pid):
            _remove_pid_file(pid_file)
            print(f"Stopped fints-rest-server with PID {pid}.")
            return 0
        time.sleep(0.1)

    print(f"Timed out while stopping server with PID {pid}.", file=sys.stderr)
    return 1


def _status_server(args: argparse.Namespace) -> int:
    pid_file = _resolve_pid_file(args.pid_file)
    pid = _read_pid(pid_file)
    if pid is None:
        print("fints-rest-server is not running.")
        return 1
    if not _process_exists(pid):
        print(f"fints-rest-server is not running. Stale PID file: {pid_file}")
        return 1
    print(f"fints-rest-server is running with PID {pid}.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fints-rest-server")
    subparsers = parser.add_subparsers(dest="command", required=True)

    start_parser = subparsers.add_parser("start", help="Start the REST API server in the background")
    start_parser.add_argument("--env-file", type=Path, help="Load environment variables from this file before resolving defaults")
    start_parser.add_argument("--host")
    start_parser.add_argument("--port", type=int)
    start_parser.add_argument("--pid-file", type=Path)
    start_parser.add_argument("--log-file", type=Path)
    start_parser.set_defaults(handler=_start_server)

    stop_parser = subparsers.add_parser("stop", help="Stop the background REST API server")
    stop_parser.add_argument("--pid-file", type=Path)
    stop_parser.set_defaults(handler=_stop_server)

    status_parser = subparsers.add_parser("status", help="Show whether the background REST API server is running")
    status_parser.add_argument("--pid-file", type=Path)
    status_parser.set_defaults(handler=_status_server)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    normalized_argv = ["--help" if arg == "-help" else arg for arg in (argv or sys.argv[1:])]
    args = parser.parse_args(normalized_argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
