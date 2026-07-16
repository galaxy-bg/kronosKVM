from pathlib import Path

from backend.app.models import Capability, HardwareStatus


def capture_devices(device_root: Path = Path("/dev")) -> list[str]:
    devices = []
    for device in sorted(device_root.glob("video*")):
        if device.name == "video0":
            devices.append(str(device))
    return devices


def capability() -> Capability:
    devices = capture_devices()
    if not devices:
        return Capability(
            name="video",
            status=HardwareStatus.WAITING_FOR_HARDWARE,
            detail="No HDMI capture device detected",
        )
    return Capability(
        name="video",
        status=HardwareStatus.DISABLED,
        detail="Capture device detected: {}".format(", ".join(devices)),
    )
