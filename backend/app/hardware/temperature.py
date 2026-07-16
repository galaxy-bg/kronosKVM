from pathlib import Path
from typing import Optional

from backend.app.models import Capability, HardwareStatus


def read_temperature(path: Path = Path("/sys/class/thermal/thermal_zone0/temp")) -> Optional[float]:
    try:
        return round(int(path.read_text(encoding="utf-8").strip()) / 1000, 1)
    except (OSError, ValueError):
        return None


def capability() -> Capability:
    value = read_temperature()
    if value is None:
        return Capability(
            name="temperature",
            status=HardwareStatus.NOT_DETECTED,
            detail="Thermal sensor is unavailable",
        )
    return Capability(
        name="temperature",
        status=HardwareStatus.READY,
        detail=f"{value:.1f} °C",
    )
