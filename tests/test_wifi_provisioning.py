import configparser
import importlib.util
import json
from types import SimpleNamespace

import pytest

from backend.app.services.device_identity import identity_from_serial
from backend.app.services.wifi_config import network_psk


@pytest.fixture
def host(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("wifi_host", "scripts/wifi-host.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "CONFIG", tmp_path / "wifi-ap.json")
    monkeypatch.setattr(module, "PROFILES", tmp_path)
    monkeypatch.setattr(module, "read_identity", lambda: identity_from_serial("100000008ed89866"))
    path = tmp_path / "ap.nmconnection"
    before = ("[connection]\nid=Old profile name\nuuid=ap-uuid\ninterface-name=wlan0\n"
              "controller=br-recovery\nport-type=bridge\n[ wifi ]\n")
    before = before.replace("[ wifi ]", "[wifi]") + "mode=ap\nssid=KDX-iKVM-8ed89866\nchannel=6\n"
    path.write_text(before)
    commands = []

    def run(args, required=True):
        commands.append(args)
        return SimpleNamespace(returncode=0, stdout="ap-uuid")

    monkeypatch.setattr(module, "run", run)
    monkeypatch.setattr(module, "performance_available", lambda: True)
    monkeypatch.setattr(module, "radio_info", lambda: {
        "frequency_mhz": 5180 if "band=a" in path.read_text() else 2437,
    })
    monkeypatch.setattr(module, "verify_radio", lambda mode: None)
    return module, path, commands, before


def psk(path):
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(path)
    return parser.get("wifi-security", "psk")


def test_open_ap_becomes_secured_without_changing_bridge_or_ethernet(host):
    module, path, commands, _ = host
    module.apply()
    assert psk(path) == network_psk("KDX@8ed89866!", "KDX-iKVM-8ed89866")
    assert "controller=br-recovery" in path.read_text()
    assert "id=Old profile name" in path.read_text()
    assert "KDX@8ed89866!" not in path.read_text()
    assert path.stat().st_mode & 0o777 == 0o600
    assert json.loads(module.CONFIG.read_text())["default"] is True
    assert not any("eth0" in command for command in commands)
    commands.clear()
    module.apply()
    assert not any("up" in command for command in commands)


def test_custom_password_survives_boot_and_ssid_change(host):
    module, path, commands, _ = host
    module.apply("Custom%WiFi!42")
    expected = psk(path)
    commands.clear()
    module.apply()
    assert psk(path) == expected
    assert not any("up" in command for command in commands)
    assert json.loads(module.CONFIG.read_text())["default"] is False
    path.write_text(path.read_text().replace("8ed89866", "12345678"))
    module.apply()
    assert psk(path) == network_psk("Custom%WiFi!42", "KDX-iKVM-12345678")


def test_existing_secured_ap_is_adopted_not_reset(host):
    module, path, _, _ = host
    path.write_text(path.read_text() + "[wifi-security]\nkey-mgmt=wpa-psk\npsk=Existing%Pass!\n")
    module.apply()
    assert psk(path) == network_psk("Existing%Pass!", "KDX-iKVM-8ed89866")
    assert json.loads(module.CONFIG.read_text())["password"] == "Existing%Pass!"


def test_default_changes_when_serial_changes_but_custom_does_not(host, monkeypatch):
    module, path, _, _ = host
    module.apply()
    monkeypatch.setattr(module, "read_identity", lambda: identity_from_serial("1000000012345678"))
    path.write_text(path.read_text().replace("8ed89866", "12345678"))
    module.apply()
    assert psk(path) == network_psk("KDX@12345678!", "KDX-iKVM-12345678")
    module.apply("Custom%WiFi!42")
    monkeypatch.setattr(module, "read_identity", lambda: identity_from_serial("100000008ed89866"))
    module.apply()
    assert json.loads(module.CONFIG.read_text())["password"] == "Custom%WiFi!42"


def test_failed_activation_restores_keyfile_and_custom_password(host, monkeypatch):
    module, path, _, _ = host
    module.apply("Original%Pass!")
    before, old_config = path.read_text(), module.CONFIG.read_text()
    original = module.run

    def fail(args, required=True):
        if required and "up" in args:
            raise RuntimeError("activation failed")
        return original(args, required)

    monkeypatch.setattr(module, "run", fail)
    with pytest.raises(RuntimeError, match="previous configuration restored"):
        module.apply("Another%Pass!")
    assert path.read_text() == before
    assert module.CONFIG.read_text() == old_config


def test_modes_preserve_credentials_and_persist_after_boot(host):
    module, path, commands, _ = host
    module.apply("Original%Pass!")
    original = psk(path)
    module.apply(mode="performance")
    assert "band=a" in path.read_text()
    assert "channel=36" in path.read_text()
    assert "channel-width=80" in path.read_text()
    assert psk(path) == original
    commands.clear()
    module.apply()
    assert json.loads(module.CONFIG.read_text())["mode"] == "performance"
    assert not any("up" in command for command in commands)
    module.apply("Changed%Pass!")
    assert "band=a" in path.read_text()
    assert json.loads(module.CONFIG.read_text())["mode"] == "performance"
    module.apply(mode="standard")
    assert "band=bg" in path.read_text()
    assert "channel=6" in path.read_text()
    assert "channel-width=20" in path.read_text()
    assert psk(path) == network_psk("Changed%Pass!", "KDX-iKVM-8ed89866")


def test_failed_5ghz_activation_falls_back_and_saves_standard(host, monkeypatch):
    module, path, _, _ = host
    module.apply("Original%Pass!")
    original = module.run

    def fail(args, required=True):
        if required and "up" in args and "band=a" in path.read_text():
            raise RuntimeError("5 GHz failed")
        return original(args, required)

    monkeypatch.setattr(module, "run", fail)
    module.apply(mode="performance")
    saved = json.loads(module.CONFIG.read_text())
    assert saved["mode"] == "standard"
    assert "returned to Standard" in saved["notice"]
    assert "band=bg" in path.read_text()
    assert psk(path) == network_psk("Original%Pass!", "KDX-iKVM-8ed89866")


def test_unavailable_5ghz_and_wrong_actual_band_fall_back(host, monkeypatch):
    module, path, _, _ = host
    module.apply()
    monkeypatch.setattr(module, "performance_available", lambda: False)
    module.apply(mode="performance")
    assert json.loads(module.CONFIG.read_text())["mode"] == "standard"
    monkeypatch.setattr(module, "performance_available", lambda: True)

    def verify(mode):
        if mode == "performance":
            raise RuntimeError("Radio stayed on wrong band")

    monkeypatch.setattr(module, "verify_radio", verify)
    module.apply(mode="performance")
    assert "band=bg" in path.read_text()
    assert json.loads(module.CONFIG.read_text())["mode"] == "standard"


def test_unchanged_saved_profile_activates_when_radio_is_not_ready_at_boot(host, monkeypatch):
    module, path, commands, _ = host
    module.apply()
    original_psk = psk(path)
    commands.clear()
    monkeypatch.setattr(module, "radio_info", lambda: {})
    module.apply()
    assert any("up" in command for command in commands)
    assert psk(path) == original_psk
    assert json.loads(module.CONFIG.read_text())["mode"] == "standard"
