from pathlib import Path

from backend.app.models import Capability, HardwareStatus


def capability(device_root: Path = Path("/dev")) -> Capability:
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
