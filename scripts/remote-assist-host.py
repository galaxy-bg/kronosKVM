#!/usr/bin/env python3
"""Restricted host-side Remote Assist controller. Never logs configuration secrets."""

import argparse
import configparser
import fcntl
import io
import ipaddress
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.services.remote_assist_config import (  # noqa: E402
    ProfileError,
    public_profile,
    validate_profile,
)

STATE = Path("/var/lib/kronoskvm/state")
PRIVATE = Path("/etc/kronoskvm/remote-assist")
CONFIG = PRIVATE / "config.json"
KEYFILE = Path("/etc/NetworkManager/system-connections/kdx-remote-assist.nmconnection")
PROFILE = "KDX-Remote-Assist"
INTERFACE = "wg-kdx"
PROFILE_UUID = "8547c45f-759e-4f75-9f6e-1fb1f452c59e"


def run(args, required=True):
    result = subprocess.run(args, capture_output=True, text=True, timeout=25, check=False)
    if required and result.returncode:
        raise RuntimeError("Host network command failed; check the VPN profile and uplink")
    return result.stdout.strip()


def read_config():
    try:
        return json.loads(CONFIG.read_text())
    except FileNotFoundError:
        return {"enabled": False, "autostart": False, "profile": None}


def atomic(path, value, public=False):
    temporary = path.with_suffix(".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream)
        if public:
            os.fchown(stream.fileno(), 10001, 20)
            os.fchmod(stream.fileno(), 0o640)
    temporary.replace(path)


def validate_routes(profile):
    local = json.loads(run(["ip", "-j", "-4", "address", "show"]))
    protected = [ipaddress.ip_network("192.168.34.0/24")]
    for device in local:
        if device["ifname"] == INTERFACE:
            continue
        for address in device.get("addr_info", []):
            protected.append(
                ipaddress.ip_network(f"{address['local']}/{address['prefixlen']}", strict=False)
            )
    networks = [ipaddress.ip_network(x.strip()) for x in profile["allowed_ips"].split(",")]
    vpn_ip = ipaddress.ip_interface(profile["address"]).ip
    if any(network.overlaps(other) for network in networks for other in protected) or any(
        vpn_ip in other for other in protected
    ):
        raise ProfileError(
            "VPN address or peer networks overlap the appliance LAN, USB WAN or recovery network"
        )
    endpoint = profile["endpoint"].rsplit(":", 1)[0]
    try:
        endpoint_ip = ipaddress.ip_address(endpoint)
    except ValueError:
        endpoint_ip = None
    if endpoint_ip and any(endpoint_ip in network for network in networks):
        raise ProfileError("VPN endpoint must be outside the peer networks")


def keyfile(config):
    profile = config["profile"]
    parser = configparser.ConfigParser(interpolation=None)
    parser["connection"] = {
        "id": PROFILE,
        "uuid": PROFILE_UUID,
        "type": "wireguard",
        "interface-name": INTERFACE,
        "autoconnect": str(config["enabled"] and config["autostart"]).lower(),
    }
    parser["wireguard"] = {
        "private-key": profile["private_key"],
        "peer-routes": "true",
        "ip4-auto-default-route": "0",
        "ip6-auto-default-route": "0",
    }
    peer = {
        "endpoint": profile["endpoint"],
        "persistent-keepalive": str(profile["keepalive"]),
        "allowed-ips": ";".join(x.strip() for x in profile["allowed_ips"].split(",")) + ";",
    }
    if profile["preshared_key"]:
        peer["preshared-key"] = profile["preshared_key"]
    parser["wireguard-peer." + profile["public_key"]] = peer
    # Only peer routes are added; an imported broad address prefix cannot claim a LAN.
    parser["ipv4"] = {
        "method": "manual",
        "address1": str(ipaddress.ip_interface(profile["address"]).ip) + "/32",
        "never-default": "true",
        "ignore-auto-dns": "true",
        "route-metric": "650",
    }
    parser["ipv6"] = {"method": "disabled"}
    stream = io.StringIO()
    parser.write(stream, space_around_delimiters=False)
    return stream.getvalue()


def install_profile(config):
    temporary = KEYFILE.with_suffix(".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(keyfile(config))
    temporary.replace(KEYFILE)
    run(["nmcli", "connection", "load", str(KEYFILE)])


def snapshot(config):
    now = int(time.time())
    profile = config.get("profile")
    active = INTERFACE in run(["wg", "show", "interfaces"], False).split()
    handshake = 0
    rx = tx = 0
    if active:
        for line in run(["wg", "show", INTERFACE, "latest-handshakes"], False).splitlines():
            fields = line.split()
            if len(fields) == 2:
                handshake = max(handshake, int(fields[1]))
        for line in run(["wg", "show", INTERFACE, "transfer"], False).splitlines():
            fields = line.split()
            if len(fields) == 3:
                rx += int(fields[1])
                tx += int(fields[2])
    state = "stop_failed" if active and not config["enabled"] else "off"
    if config["enabled"]:
        state = "setup_required" if not profile else "disconnected"
        if active:
            state = "connected" if handshake and now - handshake < 180 else "waiting_handshake"
    ports = []
    for net in Path("/sys/class/net").iterdir():
        device = (net / "device").resolve()
        if not any(p.name in {"1-1.1", "2-1"} for p in device.parents):
            continue
        driver = (net / "device/driver").resolve().name
        if driver not in {"rndis_host", "cdc_ether", "cdc_ncm", "ipheth"}:
            continue
        ports.append(
            {
                "interface": net.name,
                "driver": driver,
                "address": run(["nmcli", "-g", "IP4.ADDRESS", "device", "show", net.name], False),
                "gateway": run(["nmcli", "-g", "IP4.GATEWAY", "device", "show", net.name], False),
            }
        )
    routes = json.loads(run(["ip", "-j", "-4", "route", "show", "default"]))
    routes.sort(key=lambda item: item.get("metric", 0))
    status = {
        "installed": True,
        "updated_at": now,
        "enabled": config["enabled"],
        "autostart": config["autostart"],
        "profile": public_profile(profile) if profile else None,
        "state": state,
        "last_handshake": handshake or None,
        "rx_bytes": rx,
        "tx_bytes": tx,
        "wan": ports,
        "uplink": routes[0].get("dev") if routes else None,
        "url": "https://" + str(ipaddress.ip_interface(profile["address"]).ip) + "/"
        if profile
        else None,
        "last_result": config.get("last_result"),
    }
    atomic(STATE / "remote-assist-status.json", status, public=True)


def process(config, request):
    action = request.get("action")
    if action == "save":
        if config["enabled"] and config["profile"]:
            raise ProfileError("Turn Remote Assist off before replacing the profile")
        profile = validate_profile(request.get("profile"))
        validate_routes(profile)
        updated = {**config, "profile": profile}
        install_profile(updated)
        config.update(updated)
        if config["enabled"]:
            run(["nmcli", "--wait", "15", "connection", "up", PROFILE])
    elif action == "enable":
        config["enabled"] = True
        if config["profile"]:
            validate_routes(config["profile"])
            install_profile(config)
            run(["nmcli", "--wait", "15", "connection", "up", PROFILE])
    elif action == "disable":
        config["enabled"] = False
        if config["profile"]:
            install_profile(config)
            run(["nmcli", "connection", "down", PROFILE], False)
            if INTERFACE in run(["wg", "show", "interfaces"], False).split():
                raise RuntimeError("VPN is still active; disable could not be completed")
    elif action in {"boot-on", "boot-off"}:
        config["autostart"] = action == "boot-on"
        if config["profile"]:
            install_profile(config)
    else:
        raise ProfileError("Unsupported Remote Assist action")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", action="store_true")
    parser.add_argument("--boot", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    PRIVATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (STATE / "remote-assist.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        config = read_config()
        if args.boot and not config["autostart"]:
            config["enabled"] = False
            if config["profile"]:
                install_profile(config)
            atomic(CONFIG, config)
        target = STATE / "remote-assist-request.json"
        if args.action and target.exists():
            request = {}
            try:
                if target.stat().st_size > 20000:
                    raise ProfileError("Request is too large")
                request = json.loads(target.read_text())
                process(config, request)
                result = {"ok": True, "message": "Settings applied"}
            except (ProfileError, RuntimeError) as error:
                result = {"ok": False, "message": str(error)}
            except Exception:
                result = {"ok": False, "message": "Host operation failed"}
            result["request_id"] = request.get("request_id") if isinstance(request, dict) else None
            config["last_result"] = result
            atomic(CONFIG, config)
            target.unlink(missing_ok=True)
        snapshot(config)


if __name__ == "__main__":
    main()
