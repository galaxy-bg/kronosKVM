import asyncio
import importlib.util
import json
import secrets
import sys
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "registration-server"))
sys.path.insert(0, str(root / "registration-server/tests"))
from test_registration import active, enroll, virtual
from test_registration import env as registration_env  # noqa: E402,F401  # noqa: E402
from app.crypto import digest  # noqa: E402
from app.models import Administrator, now  # noqa: E402

pytest_plugins = ["test_registration"]
package_spec = importlib.util.spec_from_file_location(
    "kdx_dashboard_backend",
    root / "dashboard/backend/__init__.py",
    submodule_search_locations=[str(root / "dashboard/backend")],
)
package = importlib.util.module_from_spec(package_spec)
sys.modules["kdx_dashboard_backend"] = package
package_spec.loader.exec_module(package)
spec = importlib.util.spec_from_file_location(
    "kdx_dashboard_backend.main", root / "dashboard/backend/main.py"
)
gateway = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gateway)
ORIGIN = {"Origin": "http://testserver"}


@pytest.fixture
def dashboard_env(registration_env):  # noqa: F811
    env = registration_env
    transport = httpx.ASGITransport(app=env[1])
    upstream = httpx.AsyncClient(base_url="http://registration", transport=transport)
    app = gateway.create_app(
        gateway.Settings(
            allow_lab_http=True,
            registration_url="http://registration",
            allowed_origins="http://testserver",
            static_directory="/not-present",
        ),
        upstream,
    )
    with TestClient(app) as client:
        yield client, env
    asyncio.run(upstream.aclose())


def login(pair, token=None):
    client, env = pair
    token = token or env[2]["Authorization"].removeprefix("Bearer ")
    result = client.post("/api/login", json={"token": token}, headers=ORIGIN)
    assert result.status_code == 200, result.text
    return {**ORIGIN, "X-CSRF-Token": result.json()["csrf"]}


def test_login_never_exposes_upstream_key_and_sets_httponly_cookie(dashboard_env):
    client, env = dashboard_env
    token = env[2]["Authorization"].removeprefix("Bearer ")
    result = client.post("/api/login", json={"token": token}, headers=ORIGIN)
    assert result.status_code == 200
    assert token not in result.text
    cookie = result.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert client.get("/api/session").json()["actor"]["role"] == "admin"
    assert "frame-ancestors" in result.headers["content-security-policy"]


def test_inventory_requires_session_and_reflects_real_registration_relations(dashboard_env):
    client, env = dashboard_env
    assert client.get("/api/overview").status_code == 401
    active_device = active(env)
    login(dashboard_env)
    response = client.get("/api/overview")
    assert response.status_code == 200
    data = response.json()
    assert data["devices"][0]["customer"]["name"] == "Lab"
    assert data["devices"][0]["license"]["id"] == active_device[3]
    assert len(data["customers"]) == 1 and len(data["licenses"]) == 1
    assert data["events"] and data["fetched_at"]
    assert env[2]["Authorization"].removeprefix("Bearer ") not in response.text


def test_csrf_and_origin_required_for_mutations(dashboard_env):
    client, _ = dashboard_env
    headers = login(dashboard_env)
    assert client.post("/api/customers", json={"name": "blocked"}).status_code == 403
    assert (
        client.post("/api/customers", json={"name": "blocked"}, headers=ORIGIN).status_code == 403
    )
    assert (
        client.post(
            "/api/customers",
            json={"name": "blocked"},
            headers={**headers, "Origin": "http://evil.example"},
        ).status_code
        == 403
    )
    assert (
        client.post("/api/customers", json={"name": "Valid customer"}, headers=headers).status_code
        == 200
    )


def test_viewer_cannot_mutate(dashboard_env):
    client, env = dashboard_env
    token = secrets.token_urlsafe(48)
    with env[1].state.sessions.begin() as db:
        db.add(
            Administrator(
                name="reader",
                token_hash=digest(token),
                role="viewer",
                expires_at=now() + timedelta(days=1),
            )
        )
    headers = login(dashboard_env, token)
    assert client.get("/api/tasks").status_code == 200
    assert client.delete("/api/tasks/completed",headers=headers).status_code == 403
    assert client.post("/api/tasks/events",json={"kind":"vpn_config_download","target":"00000000-0000-4000-8000-000000000001"},headers=headers).status_code == 403
    assert client.get("/api/overview").status_code == 200
    assert (
        client.post("/api/customers", json={"name": "forbidden"}, headers=headers).status_code
        == 403
    )
    assert client.post("/api/logout", headers=headers).status_code == 200


def test_logout_invalidates_cookie_and_server_session(dashboard_env):
    client, _ = dashboard_env
    headers = login(dashboard_env)
    old = client.cookies.get(gateway.COOKIE)
    assert client.post("/api/logout", headers=headers).status_code == 200
    client.cookies.set(gateway.COOKIE, old)
    assert client.get("/api/overview").status_code == 401


def test_arbitrary_upstream_paths_and_invalid_ids_rejected(dashboard_env):
    client, _ = dashboard_env
    headers = login(dashboard_env)
    assert (
        client.post(
            "/api/actions/administrators/00000000-0000-4000-8000-000000000000/delete",
            json={},
            headers=headers,
        ).status_code
        == 404
    )
    assert client.get("/api/devices/not-a-uuid").status_code == 422


def test_login_bruteforce_rate_limit(dashboard_env):
    client, _ = dashboard_env
    for _ in range(10):
        assert (
            client.post(
                "/api/login", json={"token": "not-valid-" + "x" * 40}, headers=ORIGIN
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/api/login", json={"token": "not-valid-" + "x" * 40}, headers=ORIGIN
        ).status_code
        == 429
    )


def test_reachable_upstream_revocation_is_enforced(dashboard_env):
    client, env = dashboard_env
    headers = login(dashboard_env)
    with env[1].state.sessions.begin() as db:
        db.query(Administrator).filter_by(name="test").one().active = False
    assert client.get("/api/overview").status_code == 401
    assert (
        client.post("/api/customers", json={"name": "blocked"}, headers=headers).status_code == 401
    )


def test_pending_approval_returns_token_only_for_explicit_action(dashboard_env):
    client, env = dashboard_env
    request, _ = virtual()
    device = enroll(env, request)
    headers = login(dashboard_env)
    customer = client.post(
        "/api/customers", json={"name": "Approved customer"}, headers=headers
    ).json()
    license_result = client.post(
        "/api/licenses",
        json={
            "customer_id": customer["id"],
            "kind": "DEMO",
            "max_devices": 1,
            "expires_at": (now() + timedelta(days=30)).isoformat(),
        },
        headers=headers,
    )
    assert license_result.status_code == 200
    before = client.get("/api/overview").json()
    assert before["devices"][0]["status"] == "PENDING"
    response = client.post(
        "/api/actions/devices/" + device + "/approve",
        headers=headers,
        json={
            "installation_id": request["installation_id"],
            "public_key": request["public_key"],
            "license_id": license_result.json()["id"],
            "reason": "Operator checked real identity",
        },
    )
    assert response.status_code == 200 and response.json()["activation_token"]
    after = client.get("/api/overview")
    assert response.json()["activation_token"] not in after.text
    assert after.json()["devices"][0]["status"] == "ACTIVATION_REQUIRED"


def test_upstream_unavailable_returns_controlled_error():
    async def fail(request):
        raise httpx.ConnectError("offline")

    upstream = httpx.AsyncClient(
        base_url="http://registration", transport=httpx.MockTransport(fail)
    )
    app = gateway.create_app(
        gateway.Settings(allow_lab_http=True, allowed_origins="http://testserver"), upstream
    )
    with TestClient(app) as client:
        response = client.post("/api/login", json={"token": "x" * 48}, headers=ORIGIN)
        assert response.status_code == 503
    asyncio.run(upstream.aclose())


def test_https_origin_gets_secure_cookie_while_preserving_internal_http(registration_env):  # noqa: F811
    env = registration_env
    transport = httpx.ASGITransport(app=env[1])
    upstream = httpx.AsyncClient(base_url="http://registration", transport=transport)
    app = gateway.create_app(
        gateway.Settings(
            allow_lab_http=True,
            registration_url="http://registration",
            allowed_origins="https://185.251.66.26:18443,http://testserver",
        ),
        upstream,
    )
    with TestClient(app) as client:
        token = env[2]["Authorization"].removeprefix("Bearer ")
        response = client.post(
            "/api/login", json={"token": token}, headers={"Origin": "https://185.251.66.26:18443"}
        )
        assert response.status_code == 200
        assert "; Secure" in response.headers["set-cookie"]
        local = client.post("/api/login", json={"token": token}, headers=ORIGIN)
        assert local.status_code == 200 and "; Secure" not in local.headers["set-cookie"]
    asyncio.run(upstream.aclose())
