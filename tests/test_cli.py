from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv

from easy_fints import cli


def test_status_returns_not_running_when_pid_file_missing(tmp_path, capsys):
    pid_file = tmp_path / "server.pid"

    exit_code = cli.main(["status", "--pid-file", str(pid_file)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "not running" in captured.out


def test_stop_removes_stale_pid_file(tmp_path, capsys):
    pid_file = tmp_path / "server.pid"
    pid_file.write_text("999999\n", encoding="utf-8")

    exit_code = cli.main(["stop", "--pid-file", str(pid_file)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Removed stale PID file" in captured.out
    assert not pid_file.exists()


def test_status_reports_running_process(tmp_path, capsys):
    pid_file = tmp_path / "server.pid"
    pid_file.write_text(f"{os.getpid()}\n", encoding="utf-8")

    exit_code = cli.main(["status", "--pid-file", str(pid_file)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "is running" in captured.out


def test_dash_help_is_supported(capsys):
    try:
        cli.main(["-help"])
    except SystemExit as exc:
        assert exc.code == 0
    else:
        raise AssertionError("Expected argparse to exit after printing help")

    captured = capsys.readouterr()
    assert "fints-rest-server" in captured.out


def test_start_uses_env_file_values(monkeypatch, tmp_path):
    env_file = tmp_path / "server.env"
    pid_file = tmp_path / "server.pid"
    log_file = tmp_path / "server.log"
    env_file.write_text(
        "\n".join(
            [
                "FINTS_SERVER_HOST=127.0.0.1",
                "FINTS_SERVER_PORT=9123",
                f"FINTS_SERVER_PID_FILE={pid_file}",
                f"FINTS_SERVER_LOG_FILE={log_file}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    calls: dict[str, object] = {}

    class DummyProcess:
        pid = 4242

        @staticmethod
        def poll():
            return None

    def fake_popen(command, **kwargs):
        calls["command"] = command
        calls["kwargs"] = kwargs
        return DummyProcess()

    def fake_load_project_env(default_name=".env"):
        load_dotenv(env_file, override=True)
        return env_file

    monkeypatch.setattr(cli, "load_project_env", fake_load_project_env)
    monkeypatch.setattr(cli.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(cli.time, "sleep", lambda _: None)

    exit_code = cli.main(["start", "--env-file", str(env_file)])

    assert exit_code == 0
    assert calls["command"] == [
        os.sys.executable,
        "-m",
        "uvicorn",
        "easy_fints.fastapi_app:app",
        "--host",
        "127.0.0.1",
        "--port",
        "9123",
    ]
    assert pid_file.read_text(encoding="utf-8").strip() == "4242"


def test_cli_flags_override_env(monkeypatch, tmp_path):
    env_file = tmp_path / "server.env"
    env_file.write_text(
        "FINTS_SERVER_HOST=127.0.0.1\nFINTS_SERVER_PORT=9123\n",
        encoding="utf-8",
    )

    calls: dict[str, object] = {}

    class DummyProcess:
        pid = 4343

        @staticmethod
        def poll():
            return None

    def fake_popen(command, **kwargs):
        calls["command"] = command
        return DummyProcess()

    def fake_load_project_env(default_name=".env"):
        load_dotenv(env_file, override=True)
        return env_file

    monkeypatch.setattr(cli, "load_project_env", fake_load_project_env)
    monkeypatch.setattr(cli.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(cli.time, "sleep", lambda _: None)

    exit_code = cli.main(["start", "--env-file", str(env_file), "--host", "0.0.0.0", "--port", "8001"])

    assert exit_code == 0
    assert calls["command"][-4:] == ["--host", "0.0.0.0", "--port", "8001"]
