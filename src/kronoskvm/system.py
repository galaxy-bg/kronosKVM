import os
import platform
import time
from pathlib import Path


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def get_system_info() -> dict[str, object]:
    model = _read_text(Path("/proc/device-tree/model"))
    temperature_raw = _read_text(Path("/sys/class/thermal/thermal_zone0/temp"))
    temperature = float(temperature_raw) / 1000 if temperature_raw else None

    return {
        "hostname": platform.node(),
        "model": model or "unknown",
        "architecture": platform.machine(),
        "kernel": platform.release(),
        "uptime_seconds": round(time.monotonic()),
        "load_average": list(os.getloadavg()),
        "cpu_temperature_c": temperature,
    }
