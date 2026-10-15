import importlib.util
import json
from pathlib import Path

import pytest

from backend.app.security.auth import password_hash

spec = importlib.util.spec_from_file_location("admin_reset", Path("scripts/reset-web-admin.py"))
reset = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reset)


def test_reset_restores_default_and_restarts_api(tmp_path, monkeypatch):
    path = tmp_path / "web-auth.json"
    path.write_text("old credentials")
    calls = []
    monkeypatch.setattr(reset.os, "fchown", lambda *args: None)
    reset.reset_credentials(path, runner=lambda cmd, **kwargs: calls.append(cmd))
    value = json.loads(path.read_text())
    assert value["hash"] == password_hash("ChangeMe", value["salt"])
    assert value["must_change_password"] is False
    assert path.stat().st_mode & 0o777 == 0o600
    assert calls[0] == ["docker", "stop", "kronoskvm-api"]
    assert calls[1] == ["docker", "start", "kronoskvm-api"]
    assert "ChangeMe" not in " ".join(calls[2])


def test_reset_failure_preserves_credentials_and_starts_api(tmp_path, monkeypatch):
    path = tmp_path / "web-auth.json"
    path.write_text("old credentials")
    calls = []
    monkeypatch.setattr(
        reset.os, "open", lambda *args: (_ for _ in ()).throw(OSError("write failed"))
    )
    with pytest.raises(OSError):
        reset.reset_credentials(path, runner=lambda cmd, **kwargs: calls.append(cmd))
    assert path.read_text() == "old credentials"
    assert calls[-1] == ["docker", "start", "kronoskvm-api"]


def test_reset_requires_host_root(monkeypatch):
    monkeypatch.setattr(reset.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(reset.sys, "argv", ["infrabox-reset-admin", "--yes"])
    with pytest.raises(SystemExit) as error:
        reset.main()
    assert error.value.code == 2
