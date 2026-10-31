import json
import time

import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.services import registration


@pytest.fixture
def snapshot(tmp_path, monkeypatch):
    path = tmp_path / "status.json"
    monkeypatch.setenv("KRONOSKVM_REGISTRATION_STATUS_PATH", str(path))
    monkeypatch.setattr(registration, "read_identity", lambda: {"serial": "10000000000865dd"})
    data = {
        "status": "ACTIVE",
        "authorized": True,
        "serial": "10000000000865DD",
        "checked_at": time.time(),
        "authorization_expires_at": time.time() + 3600,
        "mode": "online",
        "transport": "https",
        "device_id": "device",
        "license_id": "license",
    }
    return path, data


def test_registration_snapshot_filters_private_fields(snapshot):
    path, data = snapshot
    path.write_text(
        json.dumps(
            {
                **data,
                "private_key": "NEVER-EXPOSE",
                "activation_token": "SECRET",
                "authorization": {"signature": "PRIVATE-CACHE"},
            }
        )
    )
    response = TestClient(create_app()).get("/api/v1/system/registration")
    assert response.status_code == 200
    value = response.json()
    assert value["authorized"] and value["transport"] == "https"
    assert "NEVER-EXPOSE" not in response.text and "SECRET" not in response.text
    assert "authorization" not in value


@pytest.mark.parametrize(
    "override,reason",
    [
        ({"checked_at": 1}, "STATUS_STALE"),
        ({"authorization_expires_at": 1}, "AUTHORIZATION_EXPIRED"),
        ({"serial": "10000000DEF67890"}, "HARDWARE_MISMATCH"),
    ],
)
def test_expired_stale_or_cloned_snapshot_never_reports_authorized(snapshot, override, reason):
    path, data = snapshot
    path.write_text(json.dumps({**data, **override}))
    result = registration.read_registration_status()
    assert result["authorized"] is False and result["error"] == reason


def test_missing_and_invalid_snapshot_fail_closed(snapshot):
    path, _ = snapshot
    assert registration.read_registration_status()["status"] == "NOT_CONFIGURED"
    path.write_text("[]")
    assert registration.read_registration_status()["status"] == "UNAVAILABLE"
