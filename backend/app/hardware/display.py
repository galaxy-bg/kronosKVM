from pathlib import Path

from backend.app.models import Capability, HardwareStatus


def capability(drm_root: Path = Path("/sys/class/drm")) -> Capability:
    try:
        connected = []
        for status_path in drm_root.glob("*/status"):
            if status_path.read_text(encoding="utf-8").strip() == "connected":
                connected.append(status_path.parent.name)
    except OSError:
        connected = []

    if not connected:
        return Capability(
            name="display",
            status=HardwareStatus.NOT_DETECTED,
            detail="No connected local display detected",
        )
    return Capability(
        name="display",
        status=HardwareStatus.READY,
        detail="Connected: {}".format(", ".join(sorted(connected))),
    )
