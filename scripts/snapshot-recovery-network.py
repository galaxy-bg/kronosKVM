#!/usr/bin/env python3
"""Publish recovery link state and DHCP leases to the unprivileged API."""
import json
import os
import time
from pathlib import Path


def snapshot(lease_path=Path("/var/lib/misc/dnsmasq.leases"), net_root=Path("/sys/class/net")):
    now = time.time()
    leases = []
    try:
        lines = lease_path.read_text().splitlines()
    except OSError:
        lines = []
    for line in lines:
        fields = line.split()
        if len(fields) < 4:
            continue
        try:
            expires = int(fields[0])
        except ValueError:
            continue
        if expires and expires < now:
            continue
        leases.append({"ip": fields[2], "mac": fields[1],
                       "hostname": fields[3] if fields[3] != "*" else "Unknown device",
                       "expires_at": expires})
    ports = []
    members = net_root / "br-recovery" / "brif"
    if members.is_dir():
        for member in sorted(members.iterdir()):
            if (net_root / member.name / "wireless").exists():
                continue
            try:
                carrier = (net_root / member.name / "carrier").read_text().strip() == "1"
            except OSError:
                carrier = False
            ports.append({"interface": member.name, "connected": carrier})
    return {"updated_at": now, "ports": ports, "leases": leases}


if __name__ == "__main__":
    target = Path("/var/lib/kronoskvm/state/recovery-network.json")
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(snapshot()), encoding="utf-8")
    os.chown(temporary, 10001, 20)
    temporary.chmod(0o640)
    temporary.replace(target)
