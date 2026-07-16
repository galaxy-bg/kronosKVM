from pathlib import Path

from backend.app.models import Capability, HardwareStatus

UDC_PATH = Path("/sys/class/udc")


def controllers(path: Path = UDC_PATH) -> list[str]:
    try:
        return sorted(item.name for item in path.iterdir())
    except OSError:
        return []


def capability() -> Capability:
    detected = controllers()
    if not detected:
        return Capability(
            name="hid",
            status=HardwareStatus.NOT_DETECTED,
            detail="No USB device controller is registered",
        )
    return Capability(
        name="hid",
        status=HardwareStatus.DISABLED,
        detail="UDC detected: {}".format(", ".join(detected)),
    )
