"""Read-only access to USB filesystems mounted by the host storage helper."""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
from pathlib import Path

from fastapi import HTTPException

ROOT = Path(os.environ.get("KRONOSKVM_EXTERNAL_PATH", "/external"))
STATE = (
    Path(os.environ.get("KRONOSKVM_STATE_PATH", "/var/lib/kronoskvm/state"))
    / "external-storage.json"
)
SYS_BLOCK = Path("/sys/class/block")


def inventory() -> dict:
    try:
        data = json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {"devices": [], "status": "unavailable"}
    devices = []
    for item in data.get("devices", []):
        name = item.get("id", "")
        if not re.fullmatch(r"sd[a-z]+[0-9]*", name):
            continue
        sys_path = SYS_BLOCK / name
        try:
            resolved = sys_path.resolve(strict=True)
            disk = resolved.parent if (resolved / "partition").exists() else resolved
            if (disk / "diskseq").read_text().strip() != item["diskseq"]:
                continue
            if not {"2-1", "1-1.1"}.intersection(resolved.parts):
                continue
            result = dict(item)
            root = ROOT / name
            if item["status"] == "ready":
                mounted = root.stat()
                number = f"{os.major(mounted.st_dev)}:{os.minor(mounted.st_dev)}"
                if not root.is_mount() or number != item.get("device_number"):
                    result.update(status="connected", message="Waiting for filesystem access.")
                else:
                    # Test directory access as the unprivileged API user.
                    with os.scandir(root):
                        pass
                    usage = shutil.disk_usage(root)
                    result.update(
                        total_bytes=usage.total, used_bytes=usage.used, free_bytes=usage.free
                    )
            devices.append(result)
        except (OSError, KeyError):
            if sys_path.exists():
                devices.append(dict(item, status="connected", message="Filesystem unavailable."))
    return {"devices": devices, "status": "ready" if devices else "disconnected"}


def open_entry(device: str, relative: str = "", directory: bool = False) -> int:
    """Walk with directory descriptors so symlinks cannot escape the USB root."""
    device_info = next((x for x in inventory()["devices"] if x["id"] == device), None)
    if not device_info or device_info["status"] != "ready":
        raise HTTPException(status_code=503, detail="External storage is not ready")
    parts = relative.split("/") if relative else []
    if any(not p or p in {".", ".."} or "\\" in p or "\x00" in p for p in parts):
        raise HTTPException(status_code=400, detail="Invalid external storage path")
    fd = None
    try:
        fd = os.open(ROOT / device, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        root_device = os.fstat(fd).st_dev
        if f"{os.major(root_device)}:{os.minor(root_device)}" != device_info["device_number"]:
            raise HTTPException(status_code=503, detail="USB changed; refresh storage")
        for index, part in enumerate(parts):
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            if directory or index < len(parts) - 1:
                flags |= os.O_DIRECTORY
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
            if os.fstat(fd).st_dev != root_device:
                raise HTTPException(status_code=400, detail="Nested mounts are not supported")
        mode = os.fstat(fd).st_mode
        if not (stat.S_ISDIR(mode) if directory else stat.S_ISREG(mode)):
            raise HTTPException(status_code=400, detail="Unsupported file type")
        result, fd = fd, None
        return result
    except OSError as error:
        raise HTTPException(
            status_code=404, detail="USB file unavailable; refresh storage"
        ) from error
    finally:
        if fd is not None:
            os.close(fd)


def browse(device: str, relative: str = "") -> dict:
    fd = open_entry(device, relative, directory=True)
    try:
        files = []
        with os.scandir(fd) as entries:
            for entry in entries:
                if entry.name.startswith(".") or entry.is_symlink():
                    continue
                info = entry.stat(follow_symlinks=False)
                if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                    continue
                files.append(
                    dict(
                        name=entry.name,
                        directory=stat.S_ISDIR(info.st_mode),
                        size_bytes=info.st_size,
                    )
                )
                if len(files) >= 1000:
                    break
        files.sort(key=lambda x: (not x["directory"], x["name"].casefold()))
        return {"files": files, "path": relative, "limited": len(files) >= 1000}
    except OSError as error:
        raise HTTPException(status_code=503, detail="USB removed or unreadable") from error
    finally:
        os.close(fd)
