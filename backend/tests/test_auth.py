import json
import stat

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.app.main import create_app
from backend.app.security import auth

HEADERS = {"X-InfraBox-Request": "1", "Origin": "https://testserver"}
PASSWORD = "InfraBox-test-password-123!"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("KRONOSKVM_AUTH_PATH", str(tmp_path / "web-auth.json"))
    return TestClient(create_app(), base_url="https://testserver", headers=HEADERS)


def login(client, password="ChangeMe"):
    return client.post("/api/v1/auth/login", json={"username": "admin", "password": password})


def activate(client):
    assert login(client).status_code == 200
    response = client.post(
        "/api/v1/auth/password",
        json={
            "current_password": "ChangeMe",
            "new_password": PASSWORD,
        },
    )
    assert response.status_code == 200
    return response


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/system/info",
        "/api/v1/logs",
        "/api/v1/services",
        "/api/v1/storage",
        "/api/v1/video/latest.jpg",
        "/docs",
        "/openapi.json",
    ],
)
def test_anonymous_management_requests_are_denied(client, path):
    assert client.get(path).status_code == 401
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/auth/session").json() == {"authenticated": False}


def test_default_login_opens_dashboard_and_sets_secure_cookie(client):
    response = login(client)
    assert response.status_code == 200
    assert response.json()["must_change_password"] is False
    cookie = response.headers["set-cookie"]
    assert auth.COOKIE in cookie and "HttpOnly" in cookie and "Secure" in cookie
    assert "SameSite=strict" in cookie and "Path=/" in cookie and "Domain=" not in cookie
    assert client.get("/api/v1/system/info").status_code == 200
    assert client.get("/api/v1/auth/session").json()["must_change_password"] is False


def test_existing_first_login_flag_no_longer_blocks_management(client):
    login(client)
    client.app.state.auth.credentials["must_change_password"] = True
    assert client.get("/api/v1/system/info").status_code == 200
    assert client.get("/api/v1/auth/session").json()["must_change_password"] is False


def test_password_persists_and_default_password_stops_working(client):
    activate(client)
    assert client.get("/api/v1/system/info").status_code == 200
    path = client.app.state.auth.path
    before = path.stat().st_mtime_ns
    data = path.read_text()
    assert "ChangeMe" not in data and PASSWORD not in data
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    for _ in range(3):
        assert client.get("/api/v1/auth/session").json()["authenticated"] is True
    assert path.stat().st_mtime_ns == before
    restarted = TestClient(create_app(), base_url="https://testserver", headers=HEADERS)
    restarted.cookies.update(client.cookies)
    assert restarted.get("/api/v1/system/info").status_code == 401
    assert login(restarted).status_code == 401
    assert login(restarted, PASSWORD).status_code == 200
    assert restarted.get("/api/v1/system/info").status_code == 200


def test_password_change_and_logout_revoke_sessions(client):
    activate(client)
    other = TestClient(client.app, base_url="https://testserver", headers=HEADERS)
    assert login(other, PASSWORD).status_code == 200
    previous = client.cookies.get(auth.COOKIE)
    assert (
        client.post(
            "/api/v1/auth/password",
            json={
                "current_password": PASSWORD,
                "new_password": PASSWORD + "new",
            },
        ).status_code
        == 200
    )
    assert client.cookies.get(auth.COOKIE) != previous
    assert other.get("/api/v1/system/info").status_code == 401
    current = client.cookies.get(auth.COOKIE)
    assert client.post("/api/v1/auth/logout", json={}).status_code == 200
    assert not client.cookies.get(auth.COOKIE)
    assert (
        client.get(
            "/api/v1/system/info", headers={"Cookie": f"{auth.COOKIE}={current}"}
        ).status_code
        == 401
    )


@pytest.mark.parametrize(
    "current,new",
    [
        ("wrong", PASSWORD),
        ("ChangeMe", "ChangeMe"),
        ("ChangeMe", "short"),
    ],
)
def test_bad_password_changes_preserve_current_password(client, current, new):
    login(client)
    assert client.post(
        "/api/v1/auth/password",
        json={
            "current_password": current,
            "new_password": new,
        },
    ).status_code in {400, 422}
    assert client.get("/api/v1/system/info").status_code == 200


def test_cross_origin_and_missing_csrf_header_are_denied(client):
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "ChangeMe"},
            headers={"Origin": "https://evil.example"},
        ).status_code
        == 403
    )
    client.headers.pop("X-InfraBox-Request")
    assert login(client).status_code == 403


def test_plain_http_does_not_accept_credentials(client):
    insecure = TestClient(client.app, base_url="http://testserver", headers=HEADERS)
    assert login(insecure).status_code == 403
    assert insecure.get("/api/v1/health").status_code == 200


def test_failed_login_is_rate_limited(client):
    for _ in range(5):
        assert login(client, "wrong").status_code == 401
    response = login(client)
    assert response.status_code == 429
    assert response.headers["retry-after"] == "60"


@pytest.mark.parametrize("path", ["/api/v1/hid/ws", "/api/v1/ssh/ws", "/api/v1/serial/ws"])
def test_websocket_requires_session(client, path):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("wss://testserver" + path):
            pytest.fail("Unauthenticated console accepted")


def test_websocket_requires_same_origin_and_revokes_on_logout(client):
    activate(client)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            "wss://testserver/api/v1/hid/ws", headers={"Origin": "https://evil.example"}
        ):
            pytest.fail("Cross-origin console accepted")
    with client.websocket_connect("wss://testserver/api/v1/hid/ws") as socket:
        assert client.post("/api/v1/auth/logout", json={}).status_code == 200
        with pytest.raises(WebSocketDisconnect):
            socket.receive_text()


def test_session_idle_and_absolute_expiration(client, monkeypatch):
    activate(client)
    store = client.app.state.auth
    token = client.cookies.get(auth.COOKIE)
    baseline = auth.time.monotonic()
    monkeypatch.setattr(auth.time, "monotonic", lambda: baseline + auth.IDLE_SECONDS + 1)
    assert store.session(token) is None
    monkeypatch.setattr(auth.time, "monotonic", lambda: baseline)
    token = store._new_session()
    store.sessions[token]["last_seen"] = baseline + auth.SESSION_SECONDS
    monkeypatch.setattr(auth.time, "monotonic", lambda: baseline + auth.SESSION_SECONDS + 1)
    assert store.session(token) is None


def test_corrupt_credentials_fail_closed_without_resetting_default(client):
    path = client.app.state.auth.path
    path.write_text(json.dumps({"username": "admin", "hash": "broken"}))
    assert login(client).status_code == 503
    assert json.loads(path.read_text())["hash"] == "broken"
