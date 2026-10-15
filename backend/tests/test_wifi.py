import json
import stat
import time

import pytest
from fastapi.testclient import TestClient

from backend.app.api import wifi
from backend.app.main import create_app
from backend.app.services.wifi_config import default_password, validate_password


@pytest.mark.parametrize("value", ["short", "x" * 64, "secret\npass", "şifre1234", None, {}])
def test_password_validation_never_echoes_secrets(value):
    with pytest.raises(ValueError) as error:
        validate_password(value)
    assert str(error.value) == "Wi-Fi password must contain 8–63 printable ASCII characters"


def test_default_password_uses_last_eight_lowercase_characters():
    assert default_password("100000008ED89866") == "KDX@8ed89866!"
    with pytest.raises(ValueError):
        default_password("invalid")


def test_queue_is_private_bounded_and_status_does_not_return_secrets(tmp_path, monkeypatch):
    monkeypatch.setattr(wifi, "STATE", tmp_path)
    client = TestClient(create_app())
    status_file = tmp_path / "wifi-status.json"
    status_file.write_text(json.dumps({"installed": True, "updated_at": time.time(),
                                       "password": "never return this", "raw_psk": "secret"}))
    assert "password" not in client.get("/api/v1/network/wifi").json()
    assert "raw_psk" not in client.get("/api/v1/network/wifi").json()
    for value in [{"password": "short"}, {"password": "x" * 2000},
                  {"password": "valid-password", "path": "/etc/shadow"}]:
        response = client.put("/api/v1/network/wifi", json=value)
        assert response.status_code == 400
        assert value["password"] not in response.text
    response = client.put("/api/v1/network/wifi", json={"password": "Custom%WiFi!42"})
    assert response.status_code == 202
    request_file = tmp_path / "wifi-request.json"
    request = json.loads(request_file.read_text())
    assert request["password"] == "Custom%WiFi!42"
    assert request["request_id"] == response.json()["request_id"]
    assert stat.S_IMODE(request_file.stat().st_mode) == 0o600
    assert client.put("/api/v1/network/wifi", json={
        "password": "another password",
    }).status_code == 409
    request_file.unlink()
    status_file.write_text(json.dumps({"installed": True, "updated_at": 0}))
    assert client.put("/api/v1/network/wifi", json={
        "password": "Custom%WiFi!42",
    }).status_code == 503



def test_mode_queue_validation_does_not_allow_host_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(wifi, "STATE", tmp_path)
    (tmp_path / "wifi-status.json").write_text(json.dumps({
        "installed": True, "updated_at": time.time(), "mode": "standard",
    }))
    client = TestClient(create_app())
    for value in [{"mode": "invalid"}, {"mode": "performance", "channel": 149},
                  {"mode": "performance", "password": "Valid%Password!"}, {"mode": {}}]:
        assert client.put("/api/v1/network/wifi", json=value).status_code == 400
    response = client.put("/api/v1/network/wifi", json={"mode": "performance"})
    assert response.status_code == 202
    request = json.loads((tmp_path / "wifi-request.json").read_text())
    assert request["mode"] == "performance"
    assert "password" not in request
