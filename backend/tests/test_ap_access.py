import json
import time

import pytest
from fastapi.testclient import TestClient

from backend.app.api import ap_access
from backend.app.main import create_app
from backend.app.services.ap_access_config import firewall_rules, validate_policy


@pytest.mark.parametrize("networks", [["1.2.3.4; flush ruleset"], ["::/0"],
                                     ["192.168.34.0/24"], ["10.1.2.3/24"]])
def test_invalid_targets(networks):
    with pytest.raises(ValueError):
        validate_policy({"enabled": True, "networks": networks})


def test_rules_preserve_wifi_scope_and_disable_existing_connections():
    enabled = firewall_rules({"enabled": True, "networks": ["10.0.0.0/8"]})
    assert 'iifname "wlan0"' in enabled
    assert 'oifname "eth0"' in enabled
    assert 'ip daddr { 10.0.0.0/8 }' in enabled
    assert 'ct mark & 0x40000000 != 0' in enabled
    disabled = firewall_rules({"enabled": False, "networks": []})
    assert "masquerade" not in disabled
    assert "ct state" not in disabled
    assert 'iifname "br-recovery" oifname != "br-recovery" counter drop' in disabled
    assert "flush ruleset" not in enabled


def test_queue_default_off_validation_pending_and_stale(tmp_path, monkeypatch):
    monkeypatch.setattr(ap_access, "STATE", tmp_path)
    client = TestClient(create_app())
    assert client.get("/api/v1/network/ap-access").json()["enabled"] is False
    assert client.put("/api/v1/network/ap-access", json={"enabled": True}).status_code == 503
    (tmp_path / "ap-access-status.json").write_text(json.dumps({
        "installed": True, "updated_at": time.time(), "enabled": False,
    }))
    assert client.put("/api/v1/network/ap-access", json={
        "enabled": True, "networks": ["bad"],
    }).status_code == 400
    assert not (tmp_path / "ap-access-request.json").exists()
    assert client.put("/api/v1/network/ap-access", json={
        "enabled": True, "networks": ["192.168.1.0/24"],
    }).status_code == 202
    assert json.loads((tmp_path / "ap-access-request.json").read_text()) == {
        "enabled": True, "networks": ["192.168.1.0/24"],
    }
    assert client.put("/api/v1/network/ap-access", json={"enabled": False}).status_code == 409
