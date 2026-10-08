"""Deterministic InfraBox names from the full Raspberry Pi hardware serial."""

import re
from pathlib import Path

SERIAL_PATHS = (
    Path("/sys/firmware/devicetree/base/serial-number"),
    Path("/proc/device-tree/serial-number"),
    Path("/run/kronoskvm/device-tree/serial-number"),
)


def identity_from_serial(serial: str) -> dict[str, str]:
    serial = serial.strip("\x00\r\n ").lower()
    if not re.fullmatch(r"[0-9a-f]{16}", serial) or serial in {"0" * 16, "f" * 16}:
        raise ValueError("A valid 16-digit Raspberry Pi serial is required")
    suffix = serial[-8:]
    hostname = f"infrabox-{suffix}"
    return {"serial": serial, "hostname": hostname,
            "ap_ssid": f"KDX-iKVM-{suffix}", "mdns": f"{hostname}.local"}


def read_identity(paths=SERIAL_PATHS, cpuinfo=Path("/proc/cpuinfo")) -> dict[str, str]:
    for path in paths:
        try:
            return identity_from_serial(path.read_text(encoding="ascii"))
        except (OSError, UnicodeError, ValueError):
            continue
    try:
        text = cpuinfo.read_text(encoding="ascii")
        match = re.search(r"^Serial\s*:\s*([0-9a-fA-F]{16})\s*$", text, re.M)
        if match:
            return identity_from_serial(match[1])
    except (OSError, UnicodeError, ValueError):
        pass
    raise ValueError("Raspberry Pi hardware serial is unavailable; refusing a shared identity")
