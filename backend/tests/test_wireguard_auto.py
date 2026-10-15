import base64
import importlib.util
import json
import subprocess
import time
import uuid
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from backend.app.api import remote_assist
from backend.app.main import create_app
from backend.app.services import wireguard_auto as auto
from backend.app.services.remote_assist_config import ProfileError

spec = importlib.util.spec_from_file_location("wg_ssh_enroll", Path("scripts/kdx-wg-enroll.py"))
enroll = importlib.util.module_from_spec(spec)
spec.loader.exec_module(enroll)


def key(byte):
    return base64.b64encode(bytes([byte]) * 32).decode()


def ssh_key(byte):
    blob = b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20" + bytes([byte]) * 32
    return "ssh-ed25519 " + base64.b64encode(blob).decode()


@pytest.fixture
def public():
    return {"version": 1, "device_id": "10000000000865dd", "hostname": "infrabox-000865dd",
            "public_key": key(2), "request_id": str(uuid.uuid4())}


@pytest.fixture
def reply(public):
    return {**public, "address": "10.77.0.11/32", "server_public_key": key(3),
            "endpoint": "vpn.example.com:51820", "allowed_ips": "10.77.0.0/24", "keepalive": 25}


@pytest.fixture
def issuer(tmp_path, monkeypatch):
    monkeypatch.setattr(enroll, "LEASES", tmp_path / "leases")
    keys = tmp_path / "ssh" / "authorized_keys"
    keys.parent.mkdir()
    keys.write_text(ssh_key(9) + " existing-admin\n")
    monkeypatch.setattr(enroll, "AUTHORIZED_KEYS", keys)
    return keys


def test_grant_is_short_lived_forced_command_and_preserves_existing_admin_keys(issuer, public):
    before = issuer.read_text()
    grant = enroll.authorize(public["device_id"], public["hostname"], ssh_key(1),
                             "vpn.example.com:51820", 900)
    assert issuer.read_text().startswith(before)
    line = issuer.read_text().splitlines()[-1]
    assert 'restrict,expiry-time="' in line
    assert f'command="/usr/local/sbin/kdx-wg-enroll.py serve --lease {grant["lease_id"]}"' in line
    assert time.time() + 898 < grant["expires_at"] <= time.time() + 900
    assert (issuer.stat().st_mode & 0o777) == 0o600
    with pytest.raises(enroll.server.ProvisionError, match="already authorized"):
        enroll.authorize(public["device_id"], public["hostname"], ssh_key(1),
                         "vpn.example.com:51820", 900)


def test_one_grant_creates_one_peer_and_same_request_only_recovers_reply(issuer, public, reply,
                                                                      monkeypatch):
    grant = enroll.authorize(public["device_id"], public["hostname"], ssh_key(1),
                             "vpn.example.com:51820")
    manager = Mock()
    manager.records.return_value = {}
    manager.add.return_value = reply
    monkeypatch.setattr(enroll.server, "Server", lambda *a, **kw: manager)
    assert enroll.receive(grant["lease_id"], public) == reply
    assert enroll.receive(grant["lease_id"], public) == reply
    manager.add.assert_called_once_with(public)
    with pytest.raises(enroll.server.ProvisionError, match="already been used"):
        enroll.receive(grant["lease_id"], {**public, "public_key": key(5)})


def test_expired_wrong_device_and_revoked_grants_cannot_register(issuer, public, monkeypatch):
    grant = enroll.authorize(public["device_id"], public["hostname"], ssh_key(1),
                             "vpn.example.com:51820")
    manager = Mock()
    monkeypatch.setattr(enroll.server, "Server", manager)
    with pytest.raises(enroll.server.ProvisionError, match="different device"):
        enroll.receive(grant["lease_id"], {**public, "device_id": "100000008ed89866"})
    now = time.time()
    monkeypatch.setattr(enroll.time, "time", lambda: now + 1801)
    with pytest.raises(enroll.server.ProvisionError, match="expired"):
        enroll.receive(grant["lease_id"], public)
    monkeypatch.setattr(enroll.time, "time", lambda: now)
    enroll.revoke(grant["lease_id"])
    assert "existing-admin" in issuer.read_text()
    assert "kdx-enroll-" not in issuer.read_text()
    with pytest.raises(enroll.server.ProvisionError, match="revoked"):
        enroll.receive(grant["lease_id"], public)
    manager.assert_not_called()


def test_a_failed_attempt_binds_the_grant_to_one_request(issuer, public, monkeypatch):
    grant = enroll.authorize(public["device_id"], public["hostname"], ssh_key(1),
                             "vpn.example.com:51820")
    manager = Mock()
    manager.records.return_value = {}
    manager.add.side_effect = enroll.server.ProvisionError("host operation failed")
    monkeypatch.setattr(enroll.server, "Server", lambda *a, **kw: manager)
    with pytest.raises(enroll.server.ProvisionError, match="host operation failed"):
        enroll.receive(grant["lease_id"], public)
    with pytest.raises(enroll.server.ProvisionError, match="earlier request"):
        enroll.receive(grant["lease_id"], {**public, "request_id": str(uuid.uuid4())})


def test_recover_reply_after_peer_commit_but_before_lease_completion(issuer, public, reply,
                                                                  monkeypatch):
    grant = enroll.authorize(public["device_id"], public["hostname"], ssh_key(1),
                             "vpn.example.com:51820")
    manager = Mock()
    manager.records.return_value = {public["hostname"]: reply}
    monkeypatch.setattr(enroll.server, "Server", lambda *a, **kw: manager)
    assert enroll.receive(grant["lease_id"], public) == reply
    manager.add.assert_not_called()


@pytest.fixture
def transport(tmp_path, monkeypatch):
    monkeypatch.setattr(auto, "ROOT", tmp_path)
    (tmp_path / "transport.json").write_text(json.dumps({
        "host": "172.12.2.74", "port": 22, "expires_at": int(time.time()) + 900,
    }))
    (tmp_path / "known_hosts").write_text("PINNED-PUBLIC-HOST-KEY")
    (tmp_path / "id_ed25519").write_text("LOCAL-SSH-PRIVATE-DO-NOT-SEND")
    return tmp_path


def test_transport_sends_only_public_request(transport, public, reply, monkeypatch):
    calls = []

    def run(args, **kw):
        calls.append((args, kw))
        return subprocess.CompletedProcess(args, 0, json.dumps(reply))

    monkeypatch.setattr(auto.subprocess, "run", run)
    assert auto.request_registration(public) == reply
    args, kw = calls[0]
    assert "StrictHostKeyChecking=yes" in args
    assert "BatchMode=yes" in args and "IdentityAgent=none" in args
    assert "ClearAllForwardings=yes" in args and "-T" in args
    assert args[-2:] == ["root@172.12.2.74", "enroll"]
    assert json.loads(kw["input"]) == public
    assert "LOCAL-SSH-PRIVATE" not in str(calls)
    assert "private_key" not in kw["input"]
    (transport / "registration.json").write_text(json.dumps(reply))
    (transport / "transport.json").write_text(json.dumps({"host": "172.12.2.74", "expires_at": 0}))
    assert auto.request_registration(public) == reply
    assert len(calls) == 1


def test_expired_transport_or_mismatched_reply_fails_closed(transport, public, reply, monkeypatch):
    run = Mock(return_value=subprocess.CompletedProcess([], 0, json.dumps({
        **reply, "public_key": key(6),
    })))
    monkeypatch.setattr(auto.subprocess, "run", run)
    with pytest.raises(ProfileError, match="does not match"):
        auto.request_registration(public)
    (transport / "transport.json").write_text(json.dumps({"host": "172.12.2.74", "expires_at": 0}))
    assert not auto.status()["ready"]
    with pytest.raises(ProfileError, match="expired"):
        auto.request_registration(public)
    assert run.call_count == 1


def test_automatic_action_is_queued_only_with_approved_grant(transport, monkeypatch):
    monkeypatch.setattr(remote_assist, "STATE", transport)
    status = transport / "remote-assist-status.json"
    value = {"installed": True, "updated_at": time.time(), "enabled": False,
             "auto_enrollment": {"ready": False}}
    status.write_text(json.dumps(value))
    client = TestClient(create_app())
    assert client.post("/api/v1/wireguard/enroll").status_code == 409
    value["auto_enrollment"]["ready"] = True
    status.write_text(json.dumps(value))
    assert client.post("/api/v1/wireguard/enroll").status_code == 202
    queued = json.loads((transport / "remote-assist-request.json").read_text())
    assert queued["action"] == "auto-register"
