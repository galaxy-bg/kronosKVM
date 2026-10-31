from pathlib import Path

from backend.app.hardware.wittypi import snapshot
from backend.app.models import Capability, HardwareStatus


def capability(device_root: Path = Path("/dev")) -> Capability:
    board = snapshot()
    if board.get("present"):
        return Capability(
            name="rtc",
            status=HardwareStatus.READY if board.get("rtc_valid") else HardwareStatus.ERROR,
            detail=(f"Witty Pi 4 RTC (UTC): {board.get('rtc_time_utc')}"
                    if board.get("rtc_valid") else "Witty Pi 4 RTC needs initialization"),
        )
    devices = sorted(device_root.glob("rtc*"))
    if not devices:
        return Capability(
            name="rtc",
            status=HardwareStatus.NOT_DETECTED,
            detail="No RTC device detected",
        )
    return Capability(
        name="rtc",
        status=HardwareStatus.READY,
        detail="RTC detected: {}".format(", ".join(str(device) for device in devices)),
    )
