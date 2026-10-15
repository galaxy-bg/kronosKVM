import base64
import importlib.util
import json
import stat
import subprocess
import uuid
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from backend.app.api import remote_assist, wireguard
from backend.app.main import create_app
from backend.app.services.remote_assist_config import ProfileError
from backend.app.services.wireguard_provisioning import registration_request, registration_response

spec = importlib.util.spec_from_file_location(
    "wg_client_host", Path("scripts/remote-assist-host.py"),
)
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)


def key(byte):
    return base64.b64encode(bytes([byte]) * 32).decode()


@pytest.fixture
def request_data():
    return {"version": 1, "device_id": "10000000000865dd", "hostname": "infrabox-000865dd",
            "public_key": key(2), "request_id": str(uuid.uuid4())}


@pytest.fixture
def response(request_data):
    return {**request_data, "address": "10.77.0.11/32", "endpoint": "vpn.example.com:51820",
            "server_public_key": key(3), "allowed_ips": "10.77.0.0/24", "keepalive": 25}


@pytest.fixture
def local(tmp_path, monkeypatch, request_data):
    private = tmp_path / "private"
    private.mkdir()
    paths = {"PRIVATE": private, "CONFIG": private / "config.json",
             "IDENTITY": private / "identity.json", "STATE": tmp_path,
             "PUBLIC_IDENTITY": tmp_path / "wireguard-enrollment.json",
             "KEYFILE": tmp_path / "wg.nmconnection", "WG_CONFIG": tmp_path / "wg-kdx.conf"}
    for k, v in paths.items():
        monkeypatch.setattr(host, k, v)
    monkeypatch.setattr(host, "read_identity", lambda: {"serial": request_data["device_id"]})
    monkeypatch.setattr(host.socket, "gethostname", lambda: request_data["hostname"])
    monkeypatch.setattr(host.os, "fchown", lambda *a: None)
    monkeypatch.setattr(host, "run",
                        lambda args, *a, **kw: key(1) if args == ["wg", "genkey"] else "")
    commands = []

    def process(args, **kw):
        commands.append((args, kw))
        if args == ["wg", "pubkey"]:
            return subprocess.CompletedProcess(args, 0, key(2))
        return subprocess.CompletedProcess(args, 3, "")

    monkeypatch.setattr(host.subprocess, "run", process)
    return {"profile": None, "enabled": False, "autostart": False}, commands


def test_identity_generated_locally_and_only_public_request_is_shared(local, request_data):
    config, commands = local
    public = host.ensure_identity(config)
    assert set(public) == set(request_data)
    assert key(1) not in json.dumps(public)
    assert "private_key" not in json.dumps(public)
    assert json.loads(host.IDENTITY.read_text())["private_key"] == key(1)
    assert json.loads(host.PUBLIC_IDENTITY.read_text()) == public
    assert stat.S_IMODE(host.IDENTITY.stat().st_mode) == 0o600
    assert stat.S_IMODE(host.PUBLIC_IDENTITY.stat().st_mode) == 0o640
    assert commands[0][1]["input"] == key(1) + "\n"
    assert all(key(1) not in str(args) for args, _ in commands)
    assert host.ensure_identity(config) == public
    assert len(commands) == 1  # Idempotent; no key rotation or network change.


def test_moved_sd_card_does_not_silently_reuse_another_boards_identity(local, monkeypatch):
    config, _ = local
    host.ensure_identity(config)
    monkeypatch.setattr(host, "read_identity", lambda: {"serial": "100000008ed89866"})
    with pytest.raises(ProfileError, match="another board"):
        host.ensure_identity(config)


def test_registration_installs_same_private_key_and_never_connects(local, response, monkeypatch):
    config, commands = local
    host.atomic(host.IDENTITY, {k: response[k] for k in (
        "version", "device_id", "hostname", "public_key", "request_id",
    )} | {"private_key": key(1)})
    monkeypatch.setattr(host, "validate_routes", lambda p: None)
    calls = []
    monkeypatch.setattr(host, "run", lambda args, *a, **kw: calls.append(args) or "")
    host.register(config, response)
    assert config["profile"]["private_key"] == key(1)
    assert config["enabled"] is False
    assert "never-default=true" in host.KEYFILE.read_text()
    assert "Address = 10.77.0.11/32" in host.WG_CONFIG.read_text()
    assert "AllowedIPs = 10.77.0.0/24" in host.WG_CONFIG.read_text()
    assert stat.S_IMODE(host.WG_CONFIG.stat().st_mode) == 0o600
    assert not any("up" in c for c in calls)
    assert not any(c[0] in {"nft", "iptables", "sysctl"} for c in calls)


@pytest.mark.parametrize("field,other", [("device_id", "100000008ed89866"),
                                        ("public_key", key(4)), ("request_id", str(uuid.uuid4()))])
def test_registration_for_other_device_or_request_is_rejected(local, response, monkeypatch,
                                                             field, other):
    config, _ = local
    public = {k: response[k] for k in (
        "version", "device_id", "hostname", "public_key", "request_id",
    )}
    host.atomic(host.IDENTITY, {**public, "private_key": key(1)})
    with pytest.raises(ProfileError, match="does not match"):
        host.register(config, {**response, field: other})
    assert not host.KEYFILE.exists()


def test_registration_file_failure_restores_previous_files(local, response, monkeypatch):
    config, _ = local
    public = {k: response[k] for k in (
        "version", "device_id", "hostname", "public_key", "request_id",
    )}
    host.atomic(host.IDENTITY, {**public, "private_key": key(1)})
    host.KEYFILE.write_text("PREVIOUS_PROFILE")
    host.WG_CONFIG.write_text("PREVIOUS_WG_CONFIG")
    monkeypatch.setattr(host, "validate_routes", lambda p: None)
    monkeypatch.setattr(host, "install_recovery_config", Mock(side_effect=OSError("disk full")))
    with pytest.raises(ProfileError, match="previous files restored"):
        host.register(config, response)
    assert host.KEYFILE.read_text() == "PREVIOUS_PROFILE"
    assert host.WG_CONFIG.read_text() == "PREVIOUS_WG_CONFIG"
    assert config["profile"] is None


def test_failed_connect_restores_autostart_files_and_previous_state(local, response, monkeypatch):
    config, _ = local
    config["profile"] = {"private_key": key(1), "public_key": key(3), "preshared_key": "",
        "name": "Office", "address": response["address"], "endpoint": response["endpoint"],
        "allowed_ips": response["allowed_ips"], "keepalive": 25}
    config["autostart"] = True
    host.KEYFILE.write_text("ORIGINAL_NM")
    host.atomic(host.CONFIG, config)
    monkeypatch.setattr(host, "validate_routes", lambda p: None)
    calls = []

    def run(args, *a, **kw):
        calls.append(args)
        if "up" in args:
            raise RuntimeError("connection failed")
        return ""

    monkeypatch.setattr(host, "run", run)
    with pytest.raises(RuntimeError, match="connection failed"):
        host.transactional_process(config, {"action": "enable"})
    assert host.KEYFILE.read_text() == "ORIGINAL_NM"
    assert config["enabled"] is False
    assert json.loads(host.CONFIG.read_text())["enabled"] is False
    assert any("down" in c for c in calls)


def test_registration_schema_rejects_secrets_full_tunnel_and_unrelated_ip(response):
    for change in ({"private_key": "NEVER-ECHO-THIS"}, {"allowed_ips": "0.0.0.0/0"},
                   {"address": "192.168.1.10/32"}, {"address": "10.77.0.11/24"},
                   {"endpoint": "vpn.example.com:51820\nPostUp=evil"}):
        with pytest.raises(ProfileError):
            registration_response({**response, **change})
    assert registration_response(response) == response
    with pytest.raises(ProfileError):
        registration_request({"private_key": "SECRET"})


def test_wireguard_api_never_echoes_private_fields_or_malformed_secret(local, response,
                                                                  tmp_path, monkeypatch):
    monkeypatch.setattr(remote_assist, "STATE", tmp_path)
    (tmp_path / "remote-assist-status.json").write_text(json.dumps({
        "installed": True, "updated_at": host.time.time(), "private_key": "TOP-SECRET",
        "profile": {"private_key": "TOP-SECRET", "endpoint": "vpn.example.com:51820"},
        "enrollment": {"private_key": "TOP-SECRET"},
    }))
    client = TestClient(create_app())
    assert "TOP-SECRET" not in client.get("/api/v1/wireguard").text
    result = client.put("/api/v1/wireguard/registration",
                        json={**response, "private_key": "SECRET"})
    assert result.status_code == 400
    assert "SECRET" not in result.text
    accepted = client.put("/api/v1/wireguard/registration", json=response)
    assert accepted.status_code == 202
    queued = json.loads((tmp_path / "remote-assist-request.json").read_text())
    assert queued["registration"] == response
    assert key(1) not in accepted.text


def test_api_rejects_identity_import_if_body_is_too_large(local, monkeypatch, tmp_path):
    monkeypatch.setattr(wireguard, "queue", lambda value: {"request_id": "test"})
    client = TestClient(create_app())
    response = client.put("/api/v1/wireguard/registration", content="x" * 5000)
    assert response.status_code == 413


def test_boot_restores_autostart_even_if_last_session_was_disconnected(local, monkeypatch):
    config, _ = local
    config.update(enabled=False, autostart=True, profile={"name": "Office"})
    host.atomic(host.CONFIG, config)
    actions = []

    def apply(config, request):
        actions.append(request["action"])
        return {**config, "enabled": True}

    monkeypatch.setattr(host, "transactional_process", apply)
    monkeypatch.setattr(host, "snapshot", lambda c: None)
    monkeypatch.setattr(host.sys, "argv", ["remote-assist-host.py", "--boot"])
    host.main()
    assert actions == ["enable"]


def test_wg_quick_conflict_rejects_registration(local, response, monkeypatch):
    config, _ = local
    monkeypatch.setattr(host.subprocess, "run", lambda *a, **kw:
                        subprocess.CompletedProcess(a, 0, ""))
    with pytest.raises(ProfileError, match="wg-quick owns"):
        host.register(config, response)
    assert not host.KEYFILE.exists()


def test_corrupt_device_keypair_is_rejected_before_profile_install(local, response, monkeypatch):
    config, _ = local
    public = {k: response[k] for k in (
        "version", "device_id", "hostname", "public_key", "request_id",
    )}
    host.atomic(host.IDENTITY, {**public, "private_key": key(1)})
    monkeypatch.setattr(host.subprocess, "run", lambda args, **kw:
                        subprocess.CompletedProcess(args, 0 if args[0] == "wg" else 3, key(5)))
    with pytest.raises(ProfileError, match="inconsistent"):
        host.register(config, response)
    assert not host.KEYFILE.exists()


def test_manual_address_change_refreshes_cached_reply(local, response, monkeypatch, tmp_path):
    config, _ = local
    public = {k: response[k] for k in (
        "version", "device_id", "hostname", "public_key", "request_id",
    )}
    host.atomic(host.IDENTITY, {**public, "private_key": key(1)})
    enrollment = tmp_path / "enrollment"
    enrollment.mkdir()
    monkeypatch.setattr(host.wireguard_auto, "ROOT", enrollment)
    host.atomic(enrollment / "registration.json", response)
    monkeypatch.setattr(host, "validate_routes", lambda p: None)
    changed = {**response, "address": "10.77.0.42/32", "endpoint": "new-vpn.example.com:51820"}
    host.register(config, changed)
    assert config["profile"]["address"] == "10.77.0.42/32"
    assert host.wireguard_auto.cached_response(public) == changed
    assert host.automatic_status(config)["state"] == "registered"
