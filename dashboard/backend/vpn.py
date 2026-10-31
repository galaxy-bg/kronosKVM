"""Read a fixed forced-command SSH snapshot; expose only a validated allowlist."""

import asyncio
import base64
import ipaddress
import json
import re
import time


def parse_snapshot(raw, devices, now=None):
    tick = int(time.time() if now is None else now)
    if len(raw) > 262144:
        raise ValueError("Snapshot too large")
    data = json.loads(raw)
    if (
        not isinstance(data, dict)
        or data.get("version") != 1
        or type(data.get("sampled_at")) is not int
        or not isinstance(data.get("peers"), list)
        or len(data["peers"]) > 1000
        or data.get("interface") != "wg0"
    ):
        raise ValueError("Invalid telemetry")
    age = tick - data["sampled_at"]
    stale = not -30 <= age <= 90
    result = {
        "sampled_at": data["sampled_at"],
        "fetched_at": tick,
        "stale": stale,
        "interface": "wg0",
        "server_endpoint": "185.251.66.26:51820",
        "protocol": "UDP",
        "server_internal_ip": "172.12.2.74",
        "interface_up": data.get("interface_up") is True,
        "error": data.get("error")
        if data.get("error") in {"INTERFACE_NOT_PRESENT", "COLLECTION_FAILED"}
        else None,
        "warning": data.get("warning")
        if data.get("warning") in {"REGISTRY_MISSING", "REGISTRY_UNAVAILABLE"}
        else None,
        "addresses": [],
        "peers": [],
    }
    for address in data.get("addresses", []):
        result["addresses"].append(str(ipaddress.ip_interface(address)))
    pub = data.get("server_public_key")
    if pub is not None:
        if not isinstance(pub, str) or len(base64.b64decode(pub, validate=True)) != 32:
            raise ValueError("Invalid key")
        result["server_public_key"] = pub
    port = data.get("listen_port")
    if port is not None:
        if type(port) is not int or not 0 < port < 65536:
            raise ValueError("Invalid port")
        result["listen_port"] = port
    device_by_serial = {d["serial"].upper(): d for d in devices if isinstance(d.get("serial"), str)}
    seen = set()
    for p in data["peers"]:
        key = p["public_key"]
        if (
            not isinstance(key, str)
            or len(base64.b64decode(key, validate=True)) != 32
            or key in seen
        ):
            raise ValueError("Invalid peer")
        seen.add(key)
        serial = p.get("hardware_serial")
        if not isinstance(serial, str) or not re.fullmatch("[0-9a-fA-F]{16}", serial):
            serial = None
        device = device_by_serial.get(serial.upper()) if serial else None
        last = p.get("last_handshake")
        if last is not None and (type(last) is not int or last < 0):
            raise ValueError("Invalid time")
        delta = tick - last if last else None
        state = (
            "unknown"
            if stale or result["error"] or not result["interface_up"]
            else "never"
            if not last
            else "recent"
            if -30 <= delta <= 180
            else "idle"
        )
        counters = {}
        for field in ("received_bytes", "sent_bytes", "keepalive_seconds"):
            n = p.get(field, 0)
            if type(n) is not int or n < 0 or n > 2**64:
                raise ValueError("Invalid counter")
            counters[field] = n
        endpoint = p.get("endpoint")
        if endpoint is not None and (not isinstance(endpoint, str) or len(endpoint) > 256):
            raise ValueError("Invalid endpoint")
        result["peers"].append(
            {
                "public_key": key,
                "name": str(p.get("name") or "")[:120],
                "hardware_serial": serial.upper() if serial else None,
                "managed": p.get("managed") is True,
                "allowed_ips": [
                    str(ipaddress.ip_network(n, strict=False)) for n in p.get("allowed_ips", [])
                ],
                "endpoint": endpoint,
                "last_handshake": last,
                "handshake_age_seconds": max(0, delta) if delta is not None else None,
                "connection_state": state,
                **counters,
                "device": {
                    "id": device["id"],
                    "serial": device["serial"],
                    "status": device["status"],
                    "model": device["model"],
                    "customer": device.get("customer"),
                    "license": {
                        "kind": device["license"]["kind"],
                        "status": device["license"]["status"],
                    }
                    if device.get("license")
                    else None,
                }
                if device
                else None,
            }
        )
    result["totals"] = {
        "peers": len(result["peers"]),
        "recent": sum(p["connection_state"] == "recent" for p in result["peers"]),
        "matched": sum(bool(p["device"]) for p in result["peers"]),
        "received_bytes": sum(p["received_bytes"] for p in result["peers"]),
        "sent_bytes": sum(p["sent_bytes"] for p in result["peers"]),
    }
    return result


class Reader:
    def __init__(self, settings):
        self.settings = settings
        self.lock = asyncio.Lock()
        self.raw = None
        self.cached_at = 0

    async def read(self, devices):
        cfg = self.settings
        if not cfg.vpn_monitor_enabled:
            return {"configured": False, "error": "NOT_CONFIGURED", "peers": []}
        async with self.lock:
            if not self.raw or time.monotonic() - self.cached_at > 15:
                process = await asyncio.create_subprocess_exec(
                    "/usr/bin/ssh",
                    "-F",
                    "/dev/null",
                    "-T",
                    "-o",
                    "BatchMode=yes",
                    "-o",
                    "IdentitiesOnly=yes",
                    "-o",
                    "IdentityAgent=none",
                    "-o",
                    "StrictHostKeyChecking=yes",
                    "-o",
                    "PasswordAuthentication=no",
                    "-o",
                    "ConnectTimeout=5",
                    "-o",
                    "ConnectionAttempts=1",
                    "-o",
                    "UserKnownHostsFile=" + cfg.vpn_known_hosts,
                    "-i",
                    cfg.vpn_ssh_key,
                    "kdx-vpn-reader@172.12.2.74",
                    "status",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                    limit=262144,
                )
                try:
                    raw, _ = await asyncio.wait_for(process.communicate(), timeout=8)
                except BaseException:
                    if process.returncode is None:
                        process.kill()
                    await process.wait()
                    raise
                if process.returncode != 0:
                    raise ValueError("VPN status transport unavailable")
                # Validate before caching; never cache a raw secret-bearing dump as API output.
                parse_snapshot(raw, devices)
                self.raw = raw
                self.cached_at = time.monotonic()
        return {"configured": True, **parse_snapshot(self.raw, devices)}
