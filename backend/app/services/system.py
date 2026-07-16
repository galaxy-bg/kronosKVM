import os
import platform
import shutil
import socket
import subprocess
import time
from pathlib import Path

from backend.app.models import (
    NetworkInfo,
    NetworkInterface,
    ServicesInfo,
    ServiceState,
    StorageInfo,
    SystemInfo,
)


def _read_text(path: Path, default: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8").rstrip("\x00\n")
    except OSError:
        return default


def get_system_info() -> SystemInfo:
    model = _read_text(Path("/proc/device-tree/model"))
    if not model:
        model = _read_text(Path("/run/kronoskvm/device-tree/model"), "unknown")
    return SystemInfo(
        hostname=socket.gethostname(),
        model=model,
        architecture=platform.machine(),
        kernel=platform.release(),
        uptime_seconds=round(time.monotonic()),
        load_average=list(os.getloadavg()),
    )


def _addresses_by_interface() -> dict[str, list[str]]:
    try:
        result = subprocess.run(
            ["/usr/sbin/ip", "-o", "address", "show"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return {}

    addresses: dict[str, list[str]] = {}
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) >= 4 and fields[2] in {"inet", "inet6"}:
            name = fields[1].split("@", 1)[0]
            addresses.setdefault(name, []).append(fields[3])
    return addresses


def get_network_info(net_root: Path = Path("/sys/class/net")) -> NetworkInfo:
    addresses = _addresses_by_interface()
    interfaces = []
    try:
        paths = sorted(net_root.iterdir())
    except OSError:
        paths = []
    for path in paths:
        interfaces.append(
            NetworkInterface(
                name=path.name,
                state=_read_text(path / "operstate", "unknown"),
                mac_address=_read_text(path / "address") or None,
                addresses=addresses.get(path.name, []),
            )
        )
    return NetworkInfo(interfaces=interfaces)


def get_storage_info() -> StorageInfo:
    usage = shutil.disk_usage("/")
    percent = round((usage.used / usage.total) * 100, 1) if usage.total else 0.0
    return StorageInfo(
        root_total_bytes=usage.total,
        root_used_bytes=usage.used,
        root_free_bytes=usage.free,
        root_percent_used=percent,
    )


def _service_state(name: str) -> str:
    try:
        result = subprocess.run(
            ["/bin/systemctl", "is-active", name],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
        return result.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def get_services_info() -> ServicesInfo:
    names = [
        "ssh.service",
        "kronoskvm-api.service",
        "kronoskvm-capture.service",
        "kronoskvm-hid.service",
        "kronoskvm-virtual-media.service",
    ]
    return ServicesInfo(
        services=[ServiceState(name=name, state=_service_state(name)) for name in names]
    )
