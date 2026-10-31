#!/usr/bin/env python3
"""Read-only WireGuard telemetry. Never use dump/private-key/preshared-keys."""

import base64
import ipaddress
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

INTERFACE = "wg0"
REGISTRY = Path("/etc/wireguard/kdx-peers.json")
OUTPUT = Path("/var/lib/kdx-vpn-monitor/status.json")
PUBLIC_FIELDS = {
    "public-key",
    "listen-port",
    "peers",
    "allowed-ips",
    "endpoints",
    "latest-handshakes",
    "transfer",
    "persistent-keepalive",
}


def run(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=5, check=False)
    if result.returncode:
        raise RuntimeError("Public WireGuard query failed")
    return result.stdout.strip()


def wg(field):
    if field not in PUBLIC_FIELDS:
        raise ValueError("Unsupported telemetry field")
    return run(["/usr/bin/wg", "show", INTERFACE, field])


def valid_key(value):
    return isinstance(value, str) and len(base64.b64decode(value, validate=True)) == 32


def rows(value):
    return {parts[0]: parts[1:] for line in value.splitlines() if (parts := line.split())}


def collect():
    sampled = int(time.time())
    data = {
        "version": 1,
        "sampled_at": sampled,
        "interface": INTERFACE,
        "server_endpoint": "185.251.66.26:51820",
        "protocol": "UDP",
        "interface_up": False,
        "peers": [],
        "source": "wireguard-readonly",
    }
    interfaces = run(["/usr/bin/wg", "show", "interfaces"]).split()
    if INTERFACE not in interfaces:
        data["error"] = "INTERFACE_NOT_PRESENT"
        return data
    address = json.loads(run(["/usr/sbin/ip", "-j", "address", "show", "dev", INTERFACE]))
    data["interface_up"] = bool(address and "UP" in address[0].get("flags", []))
    data["addresses"] = [
        str(ipaddress.ip_interface(str(v["local"]) + "/" + str(v["prefixlen"])))
        for entry in address
        for v in entry.get("addr_info", [])
        if v.get("family") in {"inet", "inet6"}
    ]
    data["server_public_key"] = wg("public-key")
    if not valid_key(data["server_public_key"]):
        raise ValueError("Invalid public key")
    data["listen_port"] = int(wg("listen-port"))
    public_keys = wg("peers").split()
    allowed = rows(wg("allowed-ips"))
    endpoints = rows(wg("endpoints"))
    handshakes = rows(wg("latest-handshakes"))
    transfer = rows(wg("transfer"))
    keepalive = rows(wg("persistent-keepalive"))
    metadata = {}
    warning = None
    try:
        registry = json.loads(REGISTRY.read_text())
        if not isinstance(registry, dict):
            raise ValueError("Invalid public registry")
        for name, record in registry.items():
            if not isinstance(record, dict):
                continue
            key = record.get("public_key")
            if not valid_key(key):
                continue
            serial = record.get("device_id")
            if not isinstance(serial, str) or not re.fullmatch("[0-9a-fA-F]{16}", serial):
                serial = None
            metadata[key] = {
                "name": str(record.get("hostname") or name)[:120],
                "hardware_serial": serial.upper() if serial else None,
            }
    except FileNotFoundError:
        warning = "REGISTRY_MISSING"
    except (OSError, ValueError, TypeError):
        warning = "REGISTRY_UNAVAILABLE"
    if warning:
        data["warning"] = warning
    for key in public_keys:
        if not valid_key(key):
            raise ValueError("Invalid peer public key")
        peer_meta = metadata.get(key, {})
        epoch = int(handshakes.get(key, ["0"])[0])
        usage = transfer.get(key, ["0", "0"])
        networks = [
            str(ipaddress.ip_network(n.strip(), strict=False))
            for n in "".join(allowed.get(key, [])).split(",")
            if n and n != "(none)"
        ]
        endpoint = "".join(endpoints.get(key, []))
        interval = "".join(keepalive.get(key, ["off"]))
        data["peers"].append(
            {
                "public_key": key,
                "name": peer_meta.get("name"),
                "hardware_serial": peer_meta.get("hardware_serial"),
                "managed": key in metadata,
                "allowed_ips": networks,
                "endpoint": None if endpoint in {"", "(none)"} else endpoint,
                "last_handshake": epoch or None,
                "received_bytes": int(usage[0]),
                "sent_bytes": int(usage[1]),
                "keepalive_seconds": int(interval) if interval.isdigit() else 0,
            }
        )
    return data


def save(value):
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".snapshot-", dir=str(OUTPUT.parent))
    try:
        with os.fdopen(fd, "w") as stream:
            os.fchmod(stream.fileno(), 0o640)
            json.dump(value, stream, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, OUTPUT)
    finally:
        Path(temp).unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        save(collect())
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, subprocess.SubprocessError):
        save(
            {
                "version": 1,
                "sampled_at": int(time.time()),
                "interface": INTERFACE,
                "interface_up": False,
                "peers": [],
                "error": "COLLECTION_FAILED",
            }
        )
        raise SystemExit(1)
