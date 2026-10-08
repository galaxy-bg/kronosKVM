#!/usr/bin/env python3
"""Read or provision serial-based InfraBox names; network migration is explicit."""

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.services.device_identity import read_identity  # noqa: E402

SYSTEM_ROOT = Path("/")


def system_path(value):
    return SYSTEM_ROOT / value.lstrip("/")


def run(args, required=True):
    result = subprocess.run(args, capture_output=True, text=True, timeout=30)
    if required and result.returncode:
        raise RuntimeError(f"Command failed: {args[0]} {args[1]}")
    return result


def replace(path, text, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text() == text:
        return
    old = path.stat() if path.exists() else None
    fd, name = tempfile.mkstemp(prefix=".identity-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(text)
            os.fchmod(stream.fileno(), stat.S_IMODE(old.st_mode) if old else mode)
            if old:
                os.fchown(stream.fileno(), old.st_uid, old.st_gid)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def ap_profile():
    helper = Path(__file__).with_name("management-ap.sh")
    result = run(["bash", "-c", 'source "$1"; management_ap_uuid', "identity", str(helper)],
                 required=False)
    if result.returncode or not result.stdout.strip():
        raise RuntimeError("Provision one wlan0 AP profile before applying the AP identity")
    return result.stdout.strip()


def apply(identity, network=False, dry_run=False, boot=False):
    uuid = None
    legacy = system_path("/etc/hostapd/hostapd.conf")
    legacy_text = None
    if network:
        try:
            uuid = ap_profile()
        except (OSError, RuntimeError):
            if legacy.exists() and "interface=wlan0" in legacy.read_text().splitlines():
                legacy_text = legacy.read_text()
            elif boot:
                network = False  # Hostname remains unique before AP provisioning.
            else:
                raise
    current_ssid = run(["nmcli", "-g", "802-11-wireless.ssid", "connection", "show",
                        "uuid", uuid]).stdout.strip() if uuid else None
    print(json.dumps({**identity, "ap_profile_uuid": uuid, "dry_run": dry_run}))
    if dry_run:
        return
    if os.geteuid() != 0:
        raise RuntimeError("Run provisioning as root")
    if (network and not boot
            and system_path("/sys/class/net/eth0/carrier").read_text().strip() != "1"):
        raise RuntimeError("Ethernet must be connected before changing the AP name")
    backup_root = system_path("/var/backups/kronoskvm")
    backup_root.mkdir(parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix="device-identity-", dir=backup_root))
    os.chmod(backup, 0o700)
    old_hostname = run(["hostname"]).stdout.strip()
    (backup / "hostname.txt").write_text(old_hostname + "\n")
    if uuid:
        (backup / "ap-profile.json").write_text(json.dumps({"uuid": uuid, "ssid": current_ssid}))
    changed = []

    def save(path, content):
        previous = path.read_bytes() if path.exists() else None
        metadata = path.stat() if path.exists() else None
        if previous == content.encode():
            return
        if previous is not None:
            target = backup / path.relative_to(SYSTEM_ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        changed.append((path, previous, metadata))
        replace(path, content)
        return True

    ssid_changed = False
    try:
        hosts = system_path("/etc/hosts")
        rows = [line for line in hosts.read_text().splitlines()
                if not line.split() or line.split()[0] != "127.0.1.1"]
        save(hosts, "\n".join(rows) + f"\n127.0.1.1 {identity['hostname']}\n")
        if system_path("/etc/cloud/cloud.cfg.d").is_dir():
            save(system_path("/etc/cloud/cloud.cfg.d/99-kdx-infrabox-hostname.cfg"),
                 "preserve_hostname: true\nmanage_etc_hosts: false\n")
        save(system_path("/etc/kronoskvm/device-identity.json"), json.dumps(identity) + "\n")
        project = system_path("/opt/kronoskvm")
        if project.is_dir():
            env = project / ".env"
            rows = env.read_text().splitlines() if env.exists() else []
            rows = [line for line in rows if not line.startswith("KRONOSKVM_HOSTNAME=")]
            save(env, "\n".join(rows) + f"\nKRONOSKVM_HOSTNAME={identity['hostname']}\n")
        run(["hostnamectl", "set-hostname", identity["hostname"]])
        if network:
            dns_changed = False
            for name in ("kronoskvm-ap.conf", "kronoskvm-recovery.conf"):
                path = system_path("/etc/dnsmasq.d") / name
                if not path.exists():
                    continue
                text = path.read_text()
                text = "\n".join(
                    f"domain={identity['mdns']}" if line.startswith("domain=") else line
                    for line in text.splitlines()
                ) + "\n"
                if f"address=/{identity['mdns']}/" not in text:
                    text += (f"\nlocal=/{identity['mdns']}/\n"
                             f"address=/{identity['mdns']}/192.168.34.100\n")
                dns_changed = bool(save(path, text)) or dns_changed
            if dns_changed:
                run(["dnsmasq", "--test"])
            if uuid and current_ssid != identity["ap_ssid"]:
                ssid_changed = True
                run(["nmcli", "connection", "modify", "uuid", uuid,
                     "802-11-wireless.ssid", identity["ap_ssid"]])
                run(["nmcli", "connection", "up", "uuid", uuid])
            elif legacy_text is not None:
                rows = [line for line in legacy_text.splitlines() if not line.startswith("ssid=")]
                updated = "\n".join(rows) + f"\nssid={identity['ap_ssid']}\n"
                if updated != legacy_text:
                    save(legacy, updated)
                    run(["systemctl", "restart", "hostapd.service"])
            if dns_changed:
                run(["systemctl", "restart", "dnsmasq.service"])
        if old_hostname != identity["hostname"]:
            run(["systemctl", "try-restart", "avahi-daemon.service"], required=False)
    except Exception:
        for path, previous, metadata in reversed(changed):
            if previous is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(previous)
                os.chmod(path, stat.S_IMODE(metadata.st_mode))
                os.chown(path, metadata.st_uid, metadata.st_gid)
        run(["hostnamectl", "set-hostname", old_hostname], required=False)
        if ssid_changed:
            run(["nmcli", "connection", "modify", "uuid", uuid,
                 "802-11-wireless.ssid", current_ssid], required=False)
            run(["nmcli", "connection", "up", "uuid", uuid], required=False)
        if network:
            run(["systemctl", "restart", "dnsmasq.service"], required=False)
            if legacy_text is not None:
                run(["systemctl", "restart", "hostapd.service"], required=False)
        raise
    print(f"BACKUP={backup}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--field", choices=("serial", "hostname", "ap_ssid", "mdns"))
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true", help="Apply hostname and existing AP SSID")
    group.add_argument("--hostname-only", action="store_true", help="Provision hostname only")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--boot", action="store_true", help="Boot-time provisioning before clients")
    args = parser.parse_args()
    try:
        identity = read_identity()
        if args.apply or args.hostname_only:
            apply(identity, network=args.apply, dry_run=args.dry_run, boot=args.boot)
        else:
            print(identity[args.field] if args.field else json.dumps(identity))
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        raise SystemExit(str(error)) from None


if __name__ == "__main__":
    main()
