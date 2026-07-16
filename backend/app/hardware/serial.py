from pathlib import Path

from backend.app.models import Capability, HardwareStatus


def serial_devices(device_root: Path = Path("/dev")) -> list[str]:
    devices = list(device_root.glob("ttyUSB*")) + list(device_root.glob("ttyACM*"))
    return sorted(str(device) for device in devices)


def capability() -> Capability:
    devices = serial_devices()
    if not devices:
        return Capability(
            name="serial",
            status=HardwareStatus.NOT_DETECTED,
            detail="No USB serial adapters detected",
        )
    return Capability(
        name="serial",
        status=HardwareStatus.DISABLED,
        detail="Serial adapters detected: {}".format(", ".join(devices)),
    )
