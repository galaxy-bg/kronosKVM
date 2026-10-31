import json
import subprocess
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.app.hardware import lcd_control
from backend.app.hardware.lcd_control import LocalLCDClient


@pytest.fixture
def controller(tmp_path):
    client = LocalLCDClient(Mock(), state=tmp_path)
    yield client
    client.worker.shutdown(wait=True)


def test_power_only_uses_fixed_commands_and_unknown_input_is_rejected(controller, monkeypatch):
    commands = []
    monkeypatch.setattr(lcd_control, "run", lambda args, **kw: commands.append(args))
    assert controller.execute("reboot") == "Restarting..."
    assert controller.execute("poweroff") == "Shutting down..."
    assert commands == [["systemctl", "--no-block", "reboot"],
                        ["systemctl", "--no-block", "poweroff"]]
    with pytest.raises(ValueError):
        controller.control("reboot; touch /tmp/unwanted")


def test_ap_uses_resolved_uuid_and_verifies_live_state(controller, monkeypatch):
    commands = []
    active = [True]
    ap_uuid = "41a5b0d8-4e19-496d-b0bb-685865e92fcb"

    def command(args, required=True, **kw):
        commands.append(args)
        if args[0] == "nmcli":
            active[0] = "up" in args
        if "active_management_ap_uuid" in " ".join(args):
            return subprocess.CompletedProcess(args, 0 if active[0] else 1, ap_uuid)
        return subprocess.CompletedProcess(args, 0, ap_uuid)

    monkeypatch.setattr(lcd_control, "run", command)
    assert controller.execute("ap-off") == "Wi-Fi AP disabled until boot"
    assert controller.execute("ap-on") == "Wi-Fi AP enabled"
    assert [c for c in commands if c[0] == "nmcli"] == [
        ["nmcli", "--wait", "15", "connection", "down", "uuid", ap_uuid],
        ["nmcli", "--wait", "25", "connection", "up", "uuid", ap_uuid]]
    (controller.state / "wifi-request.json").touch()
    with pytest.raises(RuntimeError, match="pending"):
        controller.execute("ap-off")


def test_customer_access_preserves_existing_network_limits(controller, monkeypatch):
    helper = SimpleNamespace(
        read_config=lambda: {"enabled": False, "networks": ["10.2.0.0/16"]},
        apply=Mock(), atomic=Mock(), write_status=Mock(), CONFIG="private-config", OFF={
            "enabled": False, "networks": []})
    monkeypatch.setattr(controller, "host_module", lambda name: helper)
    controller.execute("access-on")
    helper.apply.assert_called_once_with({"enabled": True, "networks": ["10.2.0.0/16"]})
    assert json.loads(helper.atomic.call_args.args[1])["networks"] == ["10.2.0.0/16"]
    helper.apply.side_effect = [RuntimeError("firewall failed"), None]
    with pytest.raises(RuntimeError):
        controller.execute("access-on")
    assert helper.apply.call_args.args[0] == helper.OFF
    helper.write_status.assert_called_with(helper.OFF, "LCD policy apply failed")


def test_vpn_waits_for_correlated_result_instead_of_claiming_connected(controller):
    controller.api.action.return_value = {"request_id": "vpn-1"}
    controller.api.status.return_value = {
        "installed": True, "stale": False, "profile": {"name": "Office"},
        "state": "waiting_handshake", "last_result": {"request_id": "vpn-1", "ok": True}}
    assert controller.execute("connect") == "VPN: waiting_handshake"
    controller.api.action.assert_called_once_with("enable")
    controller.api.status.return_value = {
        "installed": True, "stale": False,
        "state": "off", "last_result": {"request_id": "vpn-1", "ok": False}}
    with pytest.raises(RuntimeError, match="failed"):
        controller.execute("disconnect")
    assert controller.api.action.call_args.args == ("disable",)


def test_worker_keeps_snapshot_nonblocking_and_rejects_duplicate_actions(controller, monkeypatch):
    entered, release = threading.Event(), threading.Event()

    def slow(action):
        entered.set()
        assert release.wait(3)
        return "Completed"

    monkeypatch.setattr(controller, "execute", slow)
    monkeypatch.setattr(controller, "refresh", lambda: None)
    request_id = controller.control("diagnostics")
    assert entered.wait(1)
    try:
        assert controller.snapshot() == {}
        with pytest.raises(RuntimeError, match="already"):
            controller.control("diagnostics")
    finally:
        release.set()
        controller.worker.shutdown(wait=True)
    assert controller.cache["result"] == {
        "request_id": request_id, "ok": True, "message": "Completed"}


def test_dns_timeout_does_not_abort_remaining_diagnostics(controller, monkeypatch):
    def command(args, required=True, **kw):
        if args[0] == "getent":
            raise subprocess.TimeoutExpired(args, 5)
        return subprocess.CompletedProcess(args, 0, "[]" if args[0] == "ip" else "")

    monkeypatch.setattr(lcd_control, "run", command)
    rows = controller.diagnostics()
    assert "DNS: Failed" in rows
    assert "Internet ping: OK" in rows


def test_missing_vpn_profile_fails_without_queuing_a_connection(controller):
    controller.api.status.return_value = {"installed": True, "stale": False, "profile": None}
    with pytest.raises(RuntimeError, match="profile required"):
        controller.execute("connect")
    controller.api.action.assert_not_called()
