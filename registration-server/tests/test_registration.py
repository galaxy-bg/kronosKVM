import base64
import os
import secrets
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.crypto import digest
from app.main import create_app
from app.models import (
    ActivationToken,
    Administrator,
    Base,
    Challenge,
    Device,
    License,
    LicenseBinding,
    RegistrationEvent,
    now,
)
from simulator.device import authenticate, verify_offline


@pytest.fixture
def env():
    url = os.environ.get("KDX_TEST_DATABASE_URL")
    engine = (
        create_engine(url)
        if url
        else create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
    )
    # PostgreSQL test database must be disposable and separate from deployment.
    if url and "test" not in engine.url.database:
        raise RuntimeError("Test database name must contain test")
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    signer = Ed25519PrivateKey.generate()
    app = create_app(Settings(allow_lab_http=True, rate_per_minute=10000), engine, signer)
    token = secrets.token_urlsafe(48)
    with app.state.sessions.begin() as db:
        db.add(
            Administrator(
                name="test",
                token_hash=digest(token),
                role="admin",
                expires_at=now() + timedelta(days=1),
            )
        )
    with TestClient(app) as client:
        yield client, app, {"Authorization": "Bearer " + token}, signer
    engine.dispose()


def virtual(serial="10000000ABC12345"):
    key = Ed25519PrivateKey.generate()
    return {
        "serial": serial,
        "installation_id": str(uuid.uuid4()),
        "public_key": base64.b64encode(
            key.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw
            )
        ).decode(),
    }, key


def enroll(env, request):
    client = env[0]
    response = client.post(
        "/api/v1/devices/enroll", json={**request, "model": "Galaxy-RP4", "firmware": "test-1"}
    )
    assert response.status_code == 200, response.text
    return response.json()["device_id"]


def provision(env, request, device_id, kind="PERPETUAL", max_devices=1, license_id=None):
    client, app, headers, _ = env
    if not license_id:
        customer = client.post(
            "/api/v1/admin/customers", json={"name": "Lab"}, headers=headers
        ).json()
        payload = {"customer_id": customer["id"], "kind": kind, "max_devices": max_devices}
        if kind != "PERPETUAL":
            payload["expires_at"] = (now() + timedelta(days=2)).isoformat()
        lic = client.post("/api/v1/admin/licenses", json=payload, headers=headers)
        assert lic.status_code == 200, lic.text
        license_id = lic.json()["id"]
    result = client.post(
        f"/api/v1/admin/devices/{device_id}/approve",
        headers=headers,
        json={
            "installation_id": request["installation_id"],
            "public_key": request["public_key"],
            "license_id": license_id,
            "reason": "Verified manufacturing inventory",
        },
    )
    assert result.status_code == 200, result.text
    return result.json()["activation_token"], license_id


def proof(env, request, key, purpose="authenticate"):
    result = env[0].post("/api/v1/devices/challenge", json={**request, "purpose": purpose})
    assert result.status_code == 200, result.text
    value = result.json()
    return {
        "challenge_id": value["challenge_id"],
        "signature": base64.b64encode(key.sign(value["message"].encode())).decode(),
    }


def active(env):
    request, key = virtual()
    device = enroll(env, request)
    token, lic = provision(env, request, device)
    result = authenticate(env[0], request, key, token)
    assert result["status"] == "ACTIVE"
    return request, key, device, lic, result


def test_new_enrollment_is_pending_and_idempotent(env):
    request, key = virtual()
    device = enroll(env, request)
    assert enroll(env, request) == device
    assert authenticate(env[0], request, key)["status"] == "PENDING"
    assert (
        env[0].get("/api/v1/admin/devices", headers=env[2]).json()[0]["ssid"] == "infrabox-ABC12345"
    )


def test_approval_and_valid_activation(env):
    request, key = virtual()
    device = enroll(env, request)
    token, _ = provision(env, request, device)
    assert authenticate(env[0], request, key)["status"] == "ACTIVATION_REQUIRED"
    assert authenticate(env[0], request, key, token)["status"] == "ACTIVE"
    with env[1].state.sessions() as db:
        stored = db.scalar(select(ActivationToken))
        assert stored.token_hash == digest(token) and stored.used_at


def test_expired_activation_token(env):
    request, key = virtual()
    device = enroll(env, request)
    token, _ = provision(env, request, device)
    with env[1].state.sessions.begin() as db:
        db.scalar(select(ActivationToken)).expires_at = now() - timedelta(seconds=1)
    result = env[0].post(
        "/api/v1/devices/activate",
        json={**proof(env, request, key, "activate"), "activation_token": token},
    )
    assert result.status_code == 401


def test_authentication_and_protected_heartbeat(env):
    request, key, device, lic, _ = active(env)
    result = authenticate(env[0], request, key)
    headers = {"Authorization": "Bearer " + result["session_token"]}
    assert env[0].get("/api/v1/devices/status", headers=headers).json()["status"] == "ACTIVE"
    assert env[0].post("/api/v1/devices/heartbeat", headers=headers).json()["status"] == "ACTIVE"
    assert env[0].get("/api/v1/devices/status").status_code == 401


def test_cloned_sd_does_not_overwrite_original(env):
    request, key, device, _, _ = active(env)
    clone = {**request, "serial": "10000000DEF67890"}
    assert (
        env[0]
        .post("/api/v1/devices/enroll", json={**clone, "model": "Pi4", "firmware": "x"})
        .status_code
        == 403
    )
    assert env[0].post("/api/v1/devices/challenge", json=clone).status_code == 403
    assert authenticate(env[0], request, key)["status"] == "ACTIVE"
    with env[1].state.sessions() as db:
        assert db.get(Device, device).serial == request["serial"]
        assert db.scalar(
            select(RegistrationEvent).where(RegistrationEvent.kind == "HARDWARE_MISMATCH")
        )


def test_reinstall_requires_explicit_recovery(env):
    request, key, device, lic, _ = active(env)
    replacement, replacement_key = virtual()
    assert enroll(env, replacement) == device
    assert authenticate(env[0], replacement, replacement_key)["status"] == "PENDING"
    payload = {
        "installation_id": replacement["installation_id"],
        "public_key": replacement["public_key"],
        "license_id": lic,
        "reason": "Replacement SD card after loss",
    }
    assert (
        env[0]
        .post(f"/api/v1/admin/devices/{device}/approve", headers=env[2], json=payload)
        .status_code
        == 409
    )
    assert (
        env[0]
        .post(
            f"/api/v1/admin/devices/{device}/reassign",
            headers=env[2],
            json={"reason": "Operator authorized reinstallation"},
        )
        .status_code
        == 200
    )
    token, _ = provision(env, replacement, device, license_id=lic)
    assert authenticate(env[0], replacement, replacement_key, token)["status"] == "ACTIVE"
    assert authenticate(env[0], request, key)["status"] == "PENDING"


def test_invalid_signature_and_consumption(env):
    request, key = virtual()
    enroll(env, request)
    value = proof(env, request, Ed25519PrivateKey.generate())
    assert env[0].post("/api/v1/devices/verify", json=value).status_code == 401
    with env[1].state.sessions() as db:
        assert db.get(Challenge, value["challenge_id"]).used_at


def test_replay_attack(env):
    request, key, _, _, _ = active(env)
    value = proof(env, request, key)
    assert env[0].post("/api/v1/devices/verify", json=value).status_code == 200
    assert env[0].post("/api/v1/devices/verify", json=value).status_code == 401


def test_expired_license(env):
    request, key, _, lic, _ = active(env)
    with env[1].state.sessions.begin() as db:
        db.get(License, lic).expires_at = now() - timedelta(seconds=1)
    result = authenticate(env[0], request, key)
    assert result["status"] == "EXPIRED" and "authorization" not in result


def test_revoked_license_and_device(env):
    request, key, device, lic, _ = active(env)
    assert (
        env[0]
        .post(
            f"/api/v1/admin/licenses/{lic}/revoke",
            headers=env[2],
            json={"reason": "License revoked by owner"},
        )
        .status_code
        == 200
    )
    assert authenticate(env[0], request, key)["status"] == "REVOKED"
    assert (
        env[0]
        .post(
            f"/api/v1/admin/devices/{device}/revoke",
            headers=env[2],
            json={"reason": "Device reported stolen"},
        )
        .status_code
        == 200
    )
    assert authenticate(env[0], request, key)["status"] == "REVOKED"


def test_unauthorized_admin_and_viewer(env):
    assert env[0].get("/api/v1/admin/devices").status_code == 401
    token = secrets.token_urlsafe(32)
    with env[1].state.sessions.begin() as db:
        db.add(
            Administrator(
                name="viewer",
                token_hash=digest(token),
                role="viewer",
                expires_at=now() + timedelta(days=1),
            )
        )
    headers = {"Authorization": "Bearer " + token}
    assert env[0].get("/api/v1/admin/devices", headers=headers).status_code == 200
    assert (
        env[0].post("/api/v1/admin/customers", json={"name": "bad"}, headers=headers).status_code
        == 403
    )


def test_concurrent_duplicate_activation(env):
    if env[1].state.sessions.kw["bind"].dialect.name != "postgresql":
        pytest.skip("Requires PostgreSQL row/transaction semantics")
    request, key = virtual()
    device = enroll(env, request)
    token, _ = provision(env, request, device)
    requests = [
        {**proof(env, request, key, "activate"), "activation_token": token} for _ in range(2)
    ]
    with ThreadPoolExecutor(2) as pool:
        results = list(
            pool.map(
                lambda payload: env[0].post("/api/v1/devices/activate", json=payload), requests
            )
        )
    assert all(r.status_code == 200 and r.json()["status"] == "ACTIVE" for r in results)
    with env[1].state.sessions() as db:
        assert len(list(db.scalars(select(LicenseBinding)))) == 1


def test_offline_grace_and_expiration(env):
    request, key, _, _, result = active(env)
    pinned = base64.b64encode(
        env[3].public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    ).decode()
    document = result["authorization"]
    issued = document["payload"]["issued_at"]
    assert verify_offline(document, pinned, request, clock=issued + 10)["status"] == "ACTIVE"
    with pytest.raises(ValueError):
        verify_offline(document, pinned, request, clock=document["payload"]["expires_at"])
    with pytest.raises(ValueError):
        verify_offline(document, pinned, {**request, "serial": "10000000DEF67890"}, clock=issued)
    with pytest.raises(ValueError):
        verify_offline(document, pinned, request, clock=issued, last_clock=issued + 100)


def test_wrong_purpose_and_expired_challenge(env):
    request, key = virtual()
    enroll(env, request)
    assert (
        env[0].post("/api/v1/devices/verify", json=proof(env, request, key, "activate")).status_code
        == 401
    )
    value = proof(env, request, key)
    with env[1].state.sessions.begin() as db:
        db.get(Challenge, value["challenge_id"]).expires_at = now() - timedelta(seconds=1)
    assert env[0].post("/api/v1/devices/verify", json=value).status_code == 401


def test_license_capacity_and_token_binding(env):
    one, key1 = virtual()
    two, key2 = virtual("10000000DEF67890")
    d1, d2 = enroll(env, one), enroll(env, two)
    t1, lic = provision(env, one, d1)
    t2, _ = provision(env, two, d2, license_id=lic)
    assert (
        env[0]
        .post(
            "/api/v1/devices/activate",
            json={**proof(env, two, key2, "activate"), "activation_token": t1},
        )
        .status_code
        == 401
    )
    assert authenticate(env[0], one, key1, t1)["status"] == "ACTIVE"
    assert (
        env[0]
        .post(
            "/api/v1/devices/activate",
            json={**proof(env, two, key2, "activate"), "activation_token": t2},
        )
        .status_code
        == 409
    )


def test_client_cannot_set_status_or_private_key(env):
    request, _ = virtual()
    response = env[0].post(
        "/api/v1/devices/enroll",
        json={**request, "model": "Pi4", "firmware": "x", "status": "ACTIVE"},
    )
    assert response.status_code == 422


def test_simulator_server_unavailable_uses_only_valid_cache(env, tmp_path, monkeypatch, capsys):
    import sys

    import httpx

    from simulator import device as simulator

    request, key, _, _, result = active(env)
    pinned = base64.b64encode(
        env[3].public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    ).decode()
    monkeypatch.setattr(simulator, "identity", lambda root, serial: (request, key))

    class Unavailable:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            raise httpx.ConnectError("simulated outage")

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(simulator.httpx, "Client", Unavailable)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "device",
            "authenticate",
            "--state",
            str(tmp_path),
            "--lab-http",
            "--server-public-key",
            pinned,
        ],
    )
    with pytest.raises(SystemExit, match="no valid offline"):
        simulator.run()
    simulator.write_private(
        tmp_path / "authorization.json",
        {"document": result["authorization"], "last_clock": 0, "denied": False},
    )
    simulator.run()
    assert "offline-grace" in capsys.readouterr().out
    simulator.write_private(
        tmp_path / "authorization.json",
        {"document": result["authorization"], "last_clock": 0, "denied": True},
    )
    with pytest.raises(SystemExit, match="no valid offline"):
        simulator.run()


def test_subscription_renew_suspend_and_transfer(env):
    request, key = virtual()
    device = enroll(env, request)
    token, lic = provision(env, request, device, kind="SUBSCRIPTION")
    assert authenticate(env[0], request, key, token)["status"] == "ACTIVE"
    reason = {"reason": "Administrative suspension review"}
    assert (
        env[0]
        .post(f"/api/v1/admin/licenses/{lic}/suspend", headers=env[2], json=reason)
        .status_code
        == 200
    )
    assert authenticate(env[0], request, key)["status"] == "SUSPENDED"
    assert (
        env[0].post(f"/api/v1/admin/licenses/{lic}/resume", headers=env[2], json=reason).status_code
        == 200
    )
    assert (
        env[0]
        .post(
            f"/api/v1/admin/licenses/{lic}/renew",
            headers=env[2],
            json={**reason, "expires_at": (now() + timedelta(days=100)).isoformat()},
        )
        .status_code
        == 200
    )
    second, second_key = virtual("1000000012345678")
    second_device = enroll(env, second)
    env[0].post(
        f"/api/v1/admin/devices/{device}/reassign", headers=env[2], json=reason
    ).raise_for_status()
    new_token, _ = provision(env, second, second_device, license_id=lic)
    assert authenticate(env[0], second, second_key, new_token)["status"] == "ACTIVE"
    assert authenticate(env[0], request, key)["status"] == "PENDING"


def test_concurrent_capacity_and_enrollment(env):
    if env[1].state.sessions.kw["bind"].dialect.name != "postgresql":
        pytest.skip("Requires PostgreSQL transaction semantics")
    one, key1 = virtual()
    with ThreadPoolExecutor(2) as pool:
        ids = list(pool.map(lambda _: enroll(env, one), range(2)))
    assert ids[0] == ids[1]
    two, key2 = virtual("10000000DEF67890")
    d2 = enroll(env, two)
    t1, lic = provision(env, one, ids[0])
    t2, _ = provision(env, two, d2, license_id=lic)
    payloads = [
        {**proof(env, one, key1, "activate"), "activation_token": t1},
        {**proof(env, two, key2, "activate"), "activation_token": t2},
    ]
    with ThreadPoolExecutor(2) as pool:
        responses = list(
            pool.map(lambda p: env[0].post("/api/v1/devices/activate", json=p), payloads)
        )
    assert sorted(r.status_code for r in responses) == [200, 409]


def test_rate_limit_and_https_required():
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    app = create_app(
        Settings(allow_lab_http=True, rate_per_minute=1), engine, Ed25519PrivateKey.generate()
    )
    with TestClient(app) as client:
        assert client.get("/api/v1/admin/devices").status_code == 401
        assert client.get("/api/v1/admin/devices").status_code == 429
        assert client.get("/health").status_code == 200
    secure = create_app(Settings(allow_lab_http=False), engine, Ed25519PrivateKey.generate())
    with TestClient(secure) as client:
        assert client.get("/api/v1/admin/devices").status_code == 400
    engine.dispose()


def test_commit_failure_does_not_return_success(env, monkeypatch):
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.orm import Session

    from app.models import Customer

    def broken_commit(self):
        raise IntegrityError("simulated commit conflict", {}, RuntimeError("conflict"))

    with monkeypatch.context() as patch:
        patch.setattr(Session, "commit", broken_commit)
        result = env[0].post(
            "/api/v1/admin/customers", headers=env[2], json={"name": "Must rollback"}
        )
    assert result.status_code == 409
    with env[1].state.sessions() as db:
        assert db.scalar(select(Customer).where(Customer.name == "Must rollback")) is None


def test_dashboard_read_endpoints_require_auth_and_expose_relations(env):
    request, _, device, license_id, _ = active(env)
    for path in ("session", "customers", "licenses", "events"):
        assert env[0].get("/api/v1/admin/" + path).status_code == 401
        result = env[0].get("/api/v1/admin/" + path, headers=env[2])
        assert result.status_code == 200
        assert "token_hash" not in result.text and "activation_token" not in result.text
    actor = env[0].get("/api/v1/admin/session", headers=env[2]).json()
    assert actor["role"] == "admin" and actor["name"] == "test"
    detail = env[0].get("/api/v1/admin/devices/" + device, headers=env[2]).json()
    assert detail["customer"]["name"] == "Lab"
    assert detail["license"]["id"] == license_id
    assert detail["license"]["device_ids"] == [device]
    assert detail["serial"] == request["serial"]
    assert env[0].get("/api/v1/admin/licenses?limit=201", headers=env[2]).status_code == 422


def test_dashboard_inventory_is_readable_by_viewer(env):
    token = secrets.token_urlsafe(32)
    with env[1].state.sessions.begin() as db:
        db.add(
            Administrator(
                name="dashboard-reader",
                token_hash=digest(token),
                role="viewer",
                expires_at=now() + timedelta(days=1),
            )
        )
    headers = {"Authorization": "Bearer " + token}
    for path in ("session", "customers", "licenses", "events"):
        assert env[0].get("/api/v1/admin/" + path, headers=headers).status_code == 200
    assert (
        env[0]
        .post("/api/v1/admin/customers", headers=headers, json={"name": "blocked"})
        .status_code
        == 403
    )


def test_active_device_reinstallation_is_visible_as_pending_review(env):
    request, key, device, license_id, _ = active(env)
    replacement, _ = virtual()
    assert enroll(env, replacement) == device
    detail = env[0].get("/api/v1/admin/devices/" + device, headers=env[2]).json()
    assert detail["status"] == "ACTIVE" and detail["license_id"] == license_id
    assert detail["pending_installations"] == [replacement["installation_id"]]
    assert request["installation_id"] not in detail["pending_installations"]
