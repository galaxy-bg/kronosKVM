from pathlib import Path
from typing import Optional

from backend.app.models import Capability, HardwareStatus, SerialDevice


def _read(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _stable_paths(device: Path, serial_root: Path) -> list[Path]:
    matches = []
    for directory in ("by-id", "by-path"):
        root = serial_root / directory
        try:
            candidates = list(root.iterdir())
        except OSError:
            continue
        for candidate in candidates:
            try:
                if candidate.resolve() == device.resolve():
                    matches.append(candidate)
            except OSError:
                continue
    return sorted(matches)


def _usb_parent(device: Path, sys_tty_root: Path) -> Optional[Path]:
    sys_device = sys_tty_root / device.name / "device"
    try:
        current = sys_device.resolve()
    except OSError:
        return None
    for parent in (current, *current.parents):
        if (parent / "idVendor").exists() and (parent / "idProduct").exists():
            return parent
    return None


def discover_devices(
    device_root: Path = Path("/dev"),
    serial_root: Path = Path("/dev/serial"),
    sys_tty_root: Path = Path("/sys/class/tty"),
) -> list[SerialDevice]:
    paths = sorted(
        list(device_root.glob("ttyUSB*")) + list(device_root.glob("ttyACM*"))
    )
    devices = []
    for path in paths:
        usb_parent = _usb_parent(path, sys_tty_root)
        stable = _stable_paths(path, serial_root)
        driver = None
        try:
            driver = (sys_tty_root / path.name / "device" / "driver").resolve().name
        except OSError:
            pass
        devices.append(
            SerialDevice(
                device=str(path),
                stable_path=str(stable[0]) if stable else None,
                vendor_id=_read(usb_parent / "idVendor") if usb_parent else None,
                product_id=_read(usb_parent / "idProduct") if usb_parent else None,
                serial_number=_read(usb_parent / "serial") if usb_parent else None,
                driver=driver,
            )
        )
    return devices


def serial_devices(device_root: Path = Path("/dev")) -> list[str]:
    return [device.device for device in discover_devices(device_root=device_root)]


def capability() -> Capability:
    devices = discover_devices()
    if not devices:
        return Capability(
            name="serial",
            status=HardwareStatus.NOT_DETECTED,
            detail="No USB serial adapters detected",
        )
    return Capability(
        name="serial",
        status=HardwareStatus.READY,
        detail=f"{len(devices)} serial adapter(s) detected",
    )
