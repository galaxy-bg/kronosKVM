#!/usr/bin/env python3
"""Fixed SSH setup command: accepts only public registration JSON on stdin."""

import importlib.util
import ipaddress
import json
import os
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "quick_wg_server", Path(__file__).with_name("kdx-wg-server.py"))
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)
SETTINGS = Path("/etc/wireguard/kdx-registration.json")


def register(value):
    if not isinstance(value, dict) or set(value) != {"request", "endpoint"}:
        raise server.ProvisionError("Invalid setup request")
    request = value["request"]
    server.validate_request(request)
    settings = json.loads(SETTINGS.read_text()) if SETTINGS.exists() else {}
    endpoint = value["endpoint"] or settings.get("endpoint")
    manager = server.Server(
        settings.get("config", "/etc/wireguard/wg0.conf"),
        settings.get("registry", "/etc/wireguard/kdx-peers.json"),
        settings.get("interface", "wg0"), settings.get("network", "10.77.0.0/24"),
        settings.get("pool_start", "10.77.0.11"), settings.get("pool_end", "10.77.0.254"),
        endpoint,
    )
    with manager.locked():
        _, file_peers, live, records = manager.inventory()
        existing = records.get(request["hostname"])
        if existing:
            if (any(existing[k] != request[k] for k in request)
                    or (endpoint and existing["endpoint"] != endpoint)):
                raise server.ProvisionError("Existing registration differs; admin review required")
            expected = [ipaddress.ip_network(existing["address"])]
            if (file_peers.get(request["public_key"]) != expected
                    or live.get(request["public_key"]) != expected):
                raise server.ProvisionError("Server peer differs from its saved registration")
            return existing
    if not endpoint:
        raise server.ProvisionError("Configure the server public VPN endpoint first")
    return manager.add(request)


def main():
    if os.geteuid() != 0:
        print("Run with approved registration permissions", file=sys.stderr)
        return 1
    os.umask(0o077)
    try:
        raw = sys.stdin.buffer.read(4097)
        if len(raw) > 4096:
            raise ValueError
        print(json.dumps(register(json.loads(raw))))
        return 0
    except Exception:
        # Never echo input, keys, credentials, commands or subprocess stderr.
        print("Registration failed; check server setup and existing peer", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
