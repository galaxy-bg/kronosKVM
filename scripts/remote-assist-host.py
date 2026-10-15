#!/usr/bin/env python3
"""Restricted host-side Remote Assist controller. Never logs configuration secrets."""

import argparse
import configparser
import copy
import fcntl
import io
import ipaddress
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.services import wireguard_auto  # noqa: E402
from backend.app.services.device_identity import read_identity  # noqa: E402
from backend.app.services.remote_assist_config import (  # noqa: E402
    ProfileError,
    public_profile,
    validate_profile,
)
from backend.app.services.wireguard_provisioning import (  # noqa: E402
    registration_request,
    registration_response,
)

STATE = Path("/var/lib/kronoskvm/state")
PRIVATE = Path("/etc/kronoskvm/remote-assist")
CONFIG = PRIVATE / "config.json"
KEYFILE = Path("/etc/NetworkManager/system-connections/kdx-remote-assist.nmconnection")
PROFILE = "KDX-Remote-Assist"
INTERFACE = "wg-kdx"
WG_CONFIG = Path("/etc/wireguard/wg-kdx.conf")
IDENTITY = PRIVATE / "identity.json"
PUBLIC_IDENTITY = STATE / "wireguard-enrollment.json"
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


def identity_public():
    try:
        saved = json.loads(IDENTITY.read_text())
    except FileNotFoundError:
        return None
    return registration_request({k: saved[k] for k in (
        "version", "device_id", "hostname", "public_key", "request_id",
    )})


def ensure_identity(config):
    if IDENTITY.exists():
        public = identity_public()
        if public["device_id"] != read_identity()["serial"]:
            raise ProfileError("VPN identity belongs to another board; operator recovery required")
        atomic(PUBLIC_IDENTITY, public, public=True)
        return public
    # A separate generated identity does not replace an existing imported profile.
    private = run(["wg", "genkey"])
    result = subprocess.run(["wg", "pubkey"], input=private + "\n", capture_output=True,
                            text=True, timeout=5)
    if result.returncode:
        raise ProfileError("Could not generate device public key")
    identity = read_identity()
    public = registration_request({"version": 1, "device_id": identity["serial"],
        "hostname": socket.gethostname(), "public_key": result.stdout.strip(),
        "request_id": str(uuid.uuid4())})
    atomic(IDENTITY, {**public, "private_key": private})
    atomic(PUBLIC_IDENTITY, public, public=True)
    return public


def backup_profile():
    backups = PRIVATE / "backups"
    backups.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="provision-", dir=backups))
    os.chmod(directory, 0o700)
    for label, path in (("config.json", CONFIG), ("profile.nmconnection", KEYFILE),
                        ("wg-kdx.conf", WG_CONFIG)):
        if path.exists():
            shutil.copy2(path, directory / label)
            os.chmod(directory / label, 0o600)
    return directory


def wireguard_file(profile):
    # NetworkManager owns wg-kdx. This root-only artifact is for recovery/export on-host;
    # wg-quick@wg-kdx must never run at the same time as the existing controller.
    return ("# Managed by KDX Remote Assist / NetworkManager; do not enable wg-quick.\n"
            "[Interface]\nPrivateKey = " + profile["private_key"] + "\nAddress = "
            + str(ipaddress.ip_interface(profile["address"]).ip) + "/32\n\n[Peer]\nPublicKey = "
            + profile["public_key"] + "\nEndpoint = " + profile["endpoint"]
            + "\nAllowedIPs = " + profile["allowed_ips"]
            + "\nPersistentKeepalive = " + str(profile["keepalive"]) + "\n"
            + ("PresharedKey = " + profile["preshared_key"] + "\n"
               if profile["preshared_key"] else ""))


def install_recovery_config(profile):
    WG_CONFIG.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = WG_CONFIG.with_suffix(".pending")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(wireguard_file(profile))
    temporary.replace(WG_CONFIG)


def register(config, metadata):
    if config["enabled"]:
        raise ProfileError("Disconnect VPN before importing a registration")
    # Do not permit a second service to fight NetworkManager over the interface.
    if subprocess.run(["systemctl", "is-active", "--quiet", "wg-quick@wg-kdx.service"],
                      capture_output=True, timeout=5).returncode == 0:
        raise ProfileError("wg-quick owns wg-kdx; resolve the service conflict first")
    response = registration_response(metadata)
    public = identity_public()
    if (not public or public["device_id"] != read_identity()["serial"]
            or any(response[k] != public[k] for k in public)):
        raise ProfileError("Registration does not match this device identity and request")
    saved = json.loads(IDENTITY.read_text())
    derived = subprocess.run(["wg", "pubkey"], input=saved["private_key"] + "\n",
                             capture_output=True, text=True, timeout=5)
    if derived.returncode or derived.stdout.strip() != public["public_key"]:
        raise ProfileError("Stored device key pair is inconsistent; operator recovery required")
    profile = validate_profile({"name": response["hostname"], "address": response["address"],
        "private_key": saved["private_key"], "public_key": response["server_public_key"],
        "endpoint": response["endpoint"], "allowed_ips": response["allowed_ips"],
        "keepalive": response["keepalive"]})
    validate_routes(profile)
    backup = backup_profile()
    before_key = KEYFILE.read_bytes() if KEYFILE.exists() else None
    before_wg = WG_CONFIG.read_bytes() if WG_CONFIG.exists() else None
    updated = {**config, "profile": profile, "enabled": False}
    try:
        install_profile(updated)
        install_recovery_config(profile)
    except Exception:
        for target, content in ((KEYFILE, before_key), (WG_CONFIG, before_wg)):
            if content is None:
                target.unlink(missing_ok=True)
            else:
                target.write_bytes(content)
                os.chmod(target, 0o600)
        if before_key is not None:
            run(["nmcli", "connection", "load", str(KEYFILE)], False)
        else:
            run(["nmcli", "connection", "delete", "uuid", PROFILE_UUID], False)
        raise ProfileError("Registration installation failed; previous files restored; "
                           "root-only backup: " + str(backup)) from None
    # Keep a previously automated device's cached public reply aligned with approved
    # manual IP/endpoint changes. A later retry must not restore obsolete settings.
    if (wireguard_auto.ROOT / "registration.json").exists():
        atomic(wireguard_auto.ROOT / "registration.json", response)
    config.update(updated)


def automatic_registration(config):
    if config.get("enabled"):
        raise ProfileError("Disconnect VPN before automatic registration")
    public = ensure_identity(config)
    response = wireguard_auto.request_registration(public)
    # Preserve the authenticated public reply before installation. Recovery needs no second grant.
    atomic(wireguard_auto.ROOT / "registration.json", response)
    register(config, response)


def automatic_status(config):
    value = wireguard_auto.status()
    if config.get("profile") and IDENTITY.exists():
        try:
            response = wireguard_auto.cached_response(identity_public())
            profile = config["profile"]
            if response and all(profile.get(k) == response[v] for k, v in (
                ("address", "address"), ("endpoint", "endpoint"),
                ("public_key", "server_public_key"), ("allowed_ips", "allowed_ips"),
            )):
                value.update(ready=False, state="registered")
        except ProfileError:
            value.update(ready=False, state="invalid_reply")
    return value


def snapshot(config):
    now = int(time.time())
    profile = config.get("profile")
    available = shutil.which("wg") is not None
    active = available and INTERFACE in run(["wg", "show", "interfaces"], False).split()
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
        "wireguard_installed": available,
        "configuration_present": KEYFILE.exists() or WG_CONFIG.exists(),
        "device_name": socket.gethostname(),
        "vpn_ip": str(ipaddress.ip_interface(profile["address"]).ip) if profile else None,
        "enrollment": identity_public(),
        "auto_enrollment": automatic_status(config),
    }
    atomic(STATE / "remote-assist-status.json", status, public=True)


def process(config, request):
    action = request.get("action")
    if action == "generate-identity":
        ensure_identity(config)
    elif action == "register":
        register(config, request.get("registration"))
    elif action == "auto-register":
        automatic_registration(config)
    elif action == "restart":
        if not config.get("profile"):
            raise ProfileError("VPN profile is required")
        validate_routes(config["profile"])
        install_profile({**config, "enabled": True})
        run(["nmcli", "connection", "down", PROFILE], False)
        run(["nmcli", "--wait", "15", "connection", "up", PROFILE])
        config["enabled"] = True
    elif action == "save":
        if config["enabled"] and config["profile"]:
            raise ProfileError("Turn Remote Assist off before replacing the profile")
        profile = validate_profile(request.get("profile"))
        validate_routes(profile)
        backup_profile()
        updated = {**config, "profile": profile}
        install_profile(updated)
        install_recovery_config(profile)
        config.update(updated)
        if config["enabled"]:
            run(["nmcli", "--wait", "15", "connection", "up", PROFILE])
    elif action == "enable":
        if not config.get("profile"):
            raise ProfileError("VPN profile is required")
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


def transactional_process(config, request):
    """Restore this profile's files and previous tunnel state if a host step fails."""
    action = request.get("action")
    if action == "generate-identity":
        candidate = copy.deepcopy(config)
        process(candidate, request)
        atomic(CONFIG, candidate)
        return candidate
    targets = (CONFIG, KEYFILE, WG_CONFIG)
    before = {path: path.read_bytes() if path.exists() else None for path in targets}
    active_before = INTERFACE in run(["wg", "show", "interfaces"], False).split()
    backup = backup_profile()
    candidate = copy.deepcopy(config)
    try:
        process(candidate, request)
        atomic(CONFIG, candidate)
        return candidate
    except Exception as error:
        changed = any((path.read_bytes() if path.exists() else None) != content
                      for path, content in before.items())
        for path, content in before.items():
            if content is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(content)
                os.chmod(path, 0o600)
        if changed or action in {"enable", "disable", "restart"}:
            try:
                if before[KEYFILE] is not None:
                    run(["nmcli", "connection", "load", str(KEYFILE)])
                    operation = "up" if active_before else "down"
                    run(["nmcli", "--wait", "15", "connection", operation, PROFILE],
                        required=active_before)
                elif changed:
                    run(["nmcli", "connection", "delete", "uuid", PROFILE_UUID], False)
            except Exception:
                raise RuntimeError("VPN rollback requires operator recovery; root-only backup: "
                                   + str(backup)) from None
        if isinstance(error, (ProfileError, RuntimeError)):
            raise
        raise RuntimeError("VPN operation failed; previous profile restored") from None


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
        if args.boot:
            if config["autostart"] and config.get("profile"):
                config = transactional_process(config, {"action": "enable"})
            else:
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
                config = transactional_process(config, request)
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
