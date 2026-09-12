#!/usr/bin/env python3
"""Mount filesystems on the dedicated storage port read-only; publish host status."""

import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path("/mnt/kronoskvm-external")
STATE = Path("/var/lib/kronoskvm/state/external-storage.json")
PORTS = {"2-1", "1-1.1"}


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=15)


def flatten(nodes):
    for node in nodes:
        yield node
        yield from flatten(node.get("children", []))


def main():
    nodes = json.loads(run("lsblk", "-J", "-o", "NAME,TYPE,FSTYPE,LABEL,SIZE", "-b").stdout)
    previous = {}
    if STATE.exists():
        previous = {item["id"]: item for item in json.loads(STATE.read_text())["devices"]}
    devices = []
    present = set()
    for node in flatten(nodes["blockdevices"]):
        name = node["name"]
        if not re.fullmatch(r"sd[a-z]+[0-9]*", name):
            continue
        if not PORTS.intersection((Path("/sys/class/block") / name).resolve().parts):
            continue
        if node["type"] == "disk" and node.get("children"):
            continue
        if node["type"] not in {"disk", "part"}:
            continue
        present.add(name)
        target = ROOT / name
        entry = dict(
            id=name,
            label=node.get("label") or name,
            filesystem=node.get("fstype"),
            size_bytes=node["size"],
            status="connected",
            message="",
            read_only=True,
        )
        sys_path = (Path("/sys/class/block") / name).resolve()
        disk = sys_path.parent if node["type"] == "part" else sys_path
        entry["diskseq"] = (disk / "diskseq").read_text().strip()
        if os.path.ismount(target) and previous.get(name, {}).get("diskseq") != entry["diskseq"]:
            run("umount", "-l", str(target))
        fs = node.get("fstype")
        if fs not in {"exfat", "vfat", "ext4"}:
            entry["message"] = (
                "Supported filesystems: exFAT, FAT and ext4. No formatting performed."
            )
        else:
            try:
                if not os.path.ismount(target):
                    target.mkdir(mode=0o755, exist_ok=True)
                    options = "ro,nosuid,nodev,noexec"
                    if fs in {"exfat", "vfat"}:
                        options += ",uid=10001,gid=20,fmask=0133,dmask=0022"
                    if fs == "ext4":
                        options += ",noload"
                    # Do not mount a filesystem already opened read-write elsewhere.
                    existing = subprocess.run(
                        ["findmnt", "-rn", "-S", "/dev/" + name, "-o", "OPTIONS"],
                        capture_output=True,
                        text=True,
                    )
                    if any("rw" in line.split(",") for line in existing.stdout.splitlines()):
                        raise RuntimeError("USB is mounted writable elsewhere; release it first.")
                    run("mount", "-t", fs, "-o", options, "/dev/" + name, str(target))
                identity = f"{os.major(target.stat().st_dev)}:{os.minor(target.stat().st_dev)}"
                if identity != (Path("/sys/class/block") / name / "dev").read_text().strip():
                    raise RuntimeError("Mount does not match the connected device.")
                entry.update(status="ready", device_number=identity)
            except (OSError, subprocess.SubprocessError, RuntimeError) as error:
                entry["message"] = (
                    str(error)
                    if isinstance(error, RuntimeError)
                    else "Unable to mount USB read-only."
                )
        devices.append(entry)
    for target in ROOT.iterdir():
        if target.name not in present and re.fullmatch(r"sd[a-z]+[0-9]*", target.name):
            if os.path.ismount(target):
                subprocess.run(["umount", "-l", str(target)], check=False, timeout=10)
            try:
                target.rmdir()
            except OSError:
                pass
    STATE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps({"devices": devices}))
    temporary.chmod(0o644)
    temporary.replace(STATE)


if __name__ == "__main__":
    main()
