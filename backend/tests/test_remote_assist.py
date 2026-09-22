import base64
import fcntl
import importlib.util
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.api import remote_assist as api
from backend.app.main import app
from backend.app.services.remote_assist_config import (
    ProfileError,
    parse_config,
    public_profile,
    validate_profile,
)

spec = importlib.util.spec_from_file_location("ra_host", Path("scripts/remote-assist-host.py"))
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)
client = TestClient(app)


@pytest.fixture
def profile():
    return {
        "name": "Office",
        "address": "10.80.0.2/24",
        "private_key": base64.b64encode(b"a" * 32).decode(),
        "public_key": base64.b64encode(b"b" * 32).decode(),
        "preshared_key": base64.b64encode(b"c" * 32).decode(),
        "endpoint": "vpn.example.com:51820",
        "allowed_ips": "10.80.0.0/24",
        "keepalive": 25,
    }


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "STATE", tmp_path)
    (tmp_path / "remote-assist-status.json").write_text(
        json.dumps({"installed": True, "updated_at": time.time(), "enabled": False})
    )
    return tmp_path


def test_secrets_stay_out_of_response_and_queue_is_private(state, profile):
    response = client.put("/api/v1/remote-assist/profile", json=profile)
    assert response.status_code == 202
    for field in ("private_key", "preshared_key"):
        assert profile[field] not in response.text
        assert field not in public_profile(validate_profile(profile))
    queued = state / "remote-assist-request.json"
    assert queued.stat().st_mode & 0o777 == 0o600
    assert json.loads(queued.read_text())["profile"]["private_key"] == profile["private_key"]
    assert client.post("/api/v1/remote-assist/disable").status_code == 409


def test_in_progress_action_cannot_be_overwritten(state):
    with (state / "remote-assist.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        assert client.post("/api/v1/remote-assist/enable").status_code == 409
    assert not (state / "remote-assist-request.json").exists()


@pytest.mark.parametrize(
    "allowed", ["0.0.0.0/0", "::/0", "127.0.0.0/8", "224.0.0.0/4", "0.0.0.0/8"]
)
def test_rejects_full_tunnel_and_special_routes(profile, allowed):
    profile["allowed_ips"] = allowed
    with pytest.raises(ProfileError):
        validate_profile(profile)


def test_rejects_hooks_and_duplicate_peers(profile):
    config = (
        f"[Interface]\nPrivateKey={profile['private_key']}\nAddress=10.80.0.2/32\n"
        f"[Peer]\nPublicKey={profile['public_key']}\nEndpoint=vpn.example.com:51820\n"
        "AllowedIPs=10.80.0.0/24\n"
    )
    assert parse_config(config, "Office")["keepalive"] == 25
    for invalid in [
        config + "PostUp=touch /tmp/oops\n",
        config + "[Peer]\n",
        config.replace("[Peer]", "DNS=1.1.1.1\n[Peer]"),
    ]:
        with pytest.raises(ProfileError):
            parse_config(invalid, "Office")


def test_validation_errors_do_not_echo_secrets(state, profile):
    profile["private_key"] = "SECRET-NOT-BASE64"
    response = client.put("/api/v1/remote-assist/profile", json=profile)
    assert response.status_code == 400
    assert profile["private_key"] not in response.text
    assert client.put("/api/v1/remote-assist/profile", json={"name": []}).status_code == 400


def test_protects_existing_lan_routes(profile, monkeypatch):
    monkeypatch.setattr(
        host,
        "run",
        lambda *a: json.dumps(
            [
                {"ifname": "eth0", "addr_info": [{"local": "192.168.1.112", "prefixlen": 24}]},
                {"ifname": "usb0", "addr_info": [{"local": "10.161.147.177", "prefixlen": 24}]},
            ]
        ),
    )
    host.validate_routes(profile)
    for network in ["192.168.1.0/24", "192.168.34.0/24", "10.0.0.0/8"]:
        with pytest.raises(ProfileError):
            host.validate_routes({**profile, "allowed_ips": network})


def test_off_disables_autoconnect_but_preserves_profile(profile, monkeypatch):
    config = {"profile": profile, "enabled": True, "autostart": True}
    installed = []
    monkeypatch.setattr(host, "install_profile", lambda c: installed.append(host.keyfile(c)))
    monkeypatch.setattr(host, "run", lambda *a: "")
    host.process(config, {"action": "disable"})
    assert config["profile"] == profile
    assert config["enabled"] is False
    assert "autoconnect=false" in installed[0]
    assert "never-default=true" in installed[0]
    assert "address1=10.80.0.2/32" in installed[0]


def test_failed_stop_is_not_reported_as_success(profile, monkeypatch):
    config = {"profile": profile, "enabled": True, "autostart": False}
    monkeypatch.setattr(host, "install_profile", lambda c: None)
    monkeypatch.setattr(host, "run", lambda args, *a: "wg-kdx" if args[0] == "wg" else "")
    with pytest.raises(RuntimeError):
        host.process(config, {"action": "disable"})


def test_initial_profile_can_be_saved_after_enable(profile, monkeypatch):
    config = {"profile": None, "enabled": True, "autostart": False}
    calls = []
    monkeypatch.setattr(host, "validate_routes", lambda p: None)
    monkeypatch.setattr(host, "install_profile", lambda c: None)
    monkeypatch.setattr(host, "run", lambda args, *a: calls.append(args) or "")
    host.process(config, {"action": "save", "profile": profile})
    assert config["profile"]["name"] == "Office"
    assert any("up" in call for call in calls)
    with pytest.raises(ProfileError):
        host.process(config, {"action": "save", "profile": profile})


def test_stale_helper_rejects_changes(state):
    (state / "remote-assist-status.json").write_text(
        json.dumps({"installed": True, "updated_at": time.time() - 60})
    )
    assert client.post("/api/v1/remote-assist/enable").status_code == 503
