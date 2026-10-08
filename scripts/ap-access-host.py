#!/usr/bin/env python3
"""Root-only, fixed-interface AP forwarding controller."""

import argparse
import fcntl
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.services.ap_access_config import firewall_rules, validate_policy  # noqa: E402

STATE = Path("/var/lib/kronoskvm/state")
CONFIG = Path("/etc/kronoskvm/ap-access.json")
DNS = Path("/etc/dnsmasq.d/kdx-ap-access.conf")
OFF = {"enabled": False, "networks": []}


def run(args, data=None, required=True):
    result = subprocess.run(args, input=data, text=True, capture_output=True, timeout=20)
    if required and result.returncode:
        raise RuntimeError(f"Host command failed: {args[0]} {args[1]}")
    return result


def atomic(path, value, public=False):
    temporary = path.with_suffix(".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(value)
        if public:
            os.fchown(stream.fileno(), 10001, 20)
            os.fchmod(stream.fileno(), 0o640)
    temporary.replace(path)


def read_config():
    try:
        return validate_policy(json.loads(CONFIG.read_text()))
    except FileNotFoundError:
        return OFF.copy()


def apply(policy):
    # Replace only owned tables, in one atomic nft transaction.
    prefix = ""
    for family, table in [("bridge", "kdx_ap_ingress"), ("inet", "kdx_ap_access")]:
        if run(["nft", "list", "table", family, table], required=False).returncode == 0:
            prefix += f"delete table {family} {table}\n"
    rules = prefix + firewall_rules(policy)
    run(["nft", "--check", "-f", "-"], rules)
    run(["nft", "-f", "-"], rules)
    if policy["enabled"]:
        run(["sysctl", "-w", "net.ipv4.ip_forward=1"])
    # Do not turn off global forwarding needed by other host services. The owned
    # forward chain blocks AP/Recovery routed traffic even if ip_forward is on.
    options = "dhcp-option=option:router\ndhcp-option=option:dns-server\n"
    if policy["enabled"]:
        options = (
            "dhcp-option=option:router,192.168.34.100\n"
            "dhcp-option=option:dns-server,192.168.34.100\n"
        )
    previous = DNS.read_text() if DNS.exists() else ""
    if previous != options:
        atomic(DNS, options)
        run(["dnsmasq", "--test"])
        run(["systemctl", "restart", "dnsmasq.service"])


def write_status(policy, error=""):
    link = run(["cat", "/sys/class/net/eth0/carrier"], required=False).stdout.strip() == "1"
    rules = run(["nft", "list", "table", "inet", "kdx_ap_access"], required=False)
    state = "off"
    if policy["enabled"]:
        state = "active" if link else "waiting-uplink"
    if rules.returncode or error:
        state = "failed"
    atomic(STATE / "ap-access-status.json", json.dumps({
        **policy, "installed": True, "state": state, "error": error,
        "updated_at": time.time(), "uplink": "eth0", "uplink_connected": link,
        "gateway": "192.168.34.100", "ipv4_only": True,
    }), public=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--request", action="store_true")
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit("Run as root")
    with (STATE / "ap-access.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        policy = read_config()
        try:
            if args.request:
                request = STATE / "ap-access-request.json"
                try:
                    raw = request.read_text()
                finally:
                    request.unlink(missing_ok=True)
                if len(raw) > 4096:
                    raise ValueError("Policy is too large")
                policy = validate_policy(json.loads(raw))
            if args.apply or args.request:
                apply(policy)
                atomic(CONFIG, json.dumps(policy))
            write_status(policy)
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
            # Fail closed if application fails partway through a network change.
            policy = OFF.copy()
            try:
                apply(policy)
                atomic(CONFIG, json.dumps(policy))
            finally:
                write_status(policy, str(error))
            raise SystemExit(1) from None


if __name__ == "__main__":
    main()
