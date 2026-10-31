import base64
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from test_gateway import ORIGIN, dashboard_env, gateway, login, registration_env  # noqa: F401

vpn = sys.modules["kdx_dashboard_backend.vpn"]
spec = importlib.util.spec_from_file_location(
    "vpn_collector", Path(__file__).resolve().parents[1] / "vpn-monitor/collect.py"
)
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)
KEY = base64.b64encode(b"a" * 32).decode()
SERVER = base64.b64encode(b"b" * 32).decode()


def snapshot(tick=1000):
    return {
        "version": 1,
        "sampled_at": tick,
        "interface": "wg0",
        "interface_up": True,
        "addresses": ["10.77.0.1/24"],
        "listen_port": 51820,
        "server_public_key": SERVER,
        "private_key": "NEVER-SHOW",
        "peers": [
            {
                "public_key": KEY,
                "preshared_key": "NEVER-SHOW-PSK",
                "name": "infrabox-test",
                "hardware_serial": "10000000000865dd",
                "managed": True,
                "allowed_ips": ["10.77.0.11/32"],
                "endpoint": "192.0.2.1:4444",
                "last_handshake": tick - 30,
                "received_bytes": 100,
                "sent_bytes": 50,
                "keepalive_seconds": 25,
            }
        ],
    }


DEVICE = {
    "id": "device-id",
    "serial": "10000000000865DD",
    "model": "Galaxy-RP4",
    "status": "ACTIVE",
    "customer": {"id": "c", "name": "KronosDX Lab"},
    "license": {"kind": "DEMO", "status": "ACTIVE"},
}


def test_telemetry_is_allowlisted_and_matches_hardware_serial_not_license_key():
    result = vpn.parse_snapshot(json.dumps(snapshot()).encode(), [DEVICE], now=1000)
    assert "NEVER-SHOW" not in json.dumps(result)
    peer = result["peers"][0]
    assert (
        peer["device"]["id"] == "device-id" and peer["device"]["customer"]["name"] == "KronosDX Lab"
    )
    assert peer["connection_state"] == "recent" and result["totals"]["received_bytes"] == 100


@pytest.mark.parametrize(
    "last,state", [(None, "never"), (999, "recent"), (1, "idle"), (1100, "idle")]
)
def test_handshake_classification(last, state):
    data = snapshot()
    data["peers"][0]["last_handshake"] = last
    assert (
        vpn.parse_snapshot(json.dumps(data).encode(), [], now=1000)["peers"][0]["connection_state"]
        == state
    )


def test_stale_or_down_interface_never_reports_recent_peer():
    raw = json.dumps(snapshot()).encode()
    value = vpn.parse_snapshot(raw, [], now=1100)
    assert value["stale"] and value["totals"]["recent"] == 0
    data = snapshot()
    data["interface_up"] = False
    assert (
        vpn.parse_snapshot(json.dumps(data).encode(), [], now=1000)["peers"][0]["connection_state"]
        == "unknown"
    )


def test_duplicate_keys_bad_counters_and_oversized_input_rejected():
    data = snapshot()
    data["peers"].append(data["peers"][0].copy())
    with pytest.raises(ValueError):
        vpn.parse_snapshot(json.dumps(data).encode(), [], 1000)
    data = snapshot()
    data["peers"][0]["received_bytes"] = -1
    with pytest.raises(ValueError):
        vpn.parse_snapshot(json.dumps(data).encode(), [], 1000)
    with pytest.raises(ValueError):
        vpn.parse_snapshot(b" " * 262145, [], 1000)


def test_collector_uses_only_public_read_commands_and_registry_allowlist(tmp_path, monkeypatch):
    registry = tmp_path / "registry.json"
    registry.write_text(
        json.dumps(
            {
                "test": {
                    "public_key": KEY,
                    "device_id": "10000000000865dd",
                    "hostname": "infrabox-test",
                    "private_key": "DO-NOT-EXPORT",
                    "preshared_key": "DO-NOT-EXPORT",
                }
            }
        )
    )
    monkeypatch.setattr(collector, "REGISTRY", registry)
    outputs = {
        "interfaces": "wg0",
        "public-key": SERVER,
        "listen-port": "51820",
        "peers": KEY,
        "allowed-ips": KEY + "\t10.77.0.11/32",
        "endpoints": KEY + "\t192.0.2.1:4444",
        "latest-handshakes": KEY + "\t999",
        "transfer": KEY + "\t100\t50",
        "persistent-keepalive": KEY + "\t25",
    }
    seen = []

    def run(args):
        seen.append(args)
        assert args[0] in ("/usr/bin/wg", "/usr/sbin/ip")
        if args[0].endswith("/ip"):
            return json.dumps(
                [
                    {
                        "flags": ["UP"],
                        "addr_info": [{"family": "inet", "local": "10.77.0.1", "prefixlen": 24}],
                    }
                ]
            )
        assert args[1] == "show" and args[-1] not in {"dump", "private-key", "preshared-keys"}
        return outputs[args[-1]]

    monkeypatch.setattr(collector, "run", run)
    data = collector.collect()
    assert data["peers"][0]["hardware_serial"] == "10000000000865DD"
    assert "DO-NOT-EXPORT" not in json.dumps(data)
    assert seen
    with pytest.raises(ValueError):
        collector.wg("private-key")


def test_vpn_endpoint_requires_dashboard_session(dashboard_env):
    client, _ = dashboard_env
    assert client.get("/api/vpn").status_code == 401
    login(dashboard_env)
    response = client.get("/api/vpn")
    assert response.status_code == 200 and response.json()["configured"] is False


def test_vpn_endpoint_revalidates_revoked_upstream_access(dashboard_env):
    from app.models import Administrator

    client, registry = dashboard_env
    login(dashboard_env)
    with registry[1].state.sessions.begin() as db:
        db.query(Administrator).filter_by(name="test").one().active = False
    assert client.get("/api/vpn").status_code == 401


def test_reader_runs_only_fixed_host_pinned_key_and_forced_command(monkeypatch):
    import asyncio

    class Config:
        vpn_monitor_enabled = True
        vpn_ssh_key = "/etc/kdx-dashboard/test.key"
        vpn_known_hosts = "/etc/kdx-dashboard/test.hosts"

    class Process:
        returncode = 0

        async def communicate(self):
            return json.dumps(snapshot(int(__import__("time").time()))).encode(), b""

    calls = []

    async def spawn(*args, **kwargs):
        calls.append(args)
        return Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    reader = vpn.Reader(Config())

    async def scenario():
        a = await reader.read([DEVICE])
        b = await reader.read([DEVICE])
        assert a["peers"][0]["device"]["id"] == "device-id" and b["configured"]

    asyncio.run(scenario())
    assert len(calls) == 1
    command = calls[0]
    assert "StrictHostKeyChecking=yes" in command and command[-2:] == (
        "kdx-vpn-reader@172.12.2.74",
        "status",
    )
    assert "PasswordAuthentication=no" in command
