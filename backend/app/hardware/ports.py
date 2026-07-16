from pathlib import Path
from typing import Optional

from backend.app.models import PhysicalPort, PhysicalPortInventory

PORTS = (
    ("console_1", "Console 1", "USB1", "1-1.1"),
    ("console_2", "Console 2", "USB2", "1-1.2"),
    ("service_usb", "Service USB", "USB3", "1-1.3"),
    ("target_lan", "Target LAN", "ETH1", "1-1.5"),
)


def _read(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _serial_device_for(
    usb_path: str,
    tty_root: Path,
) -> Optional[str]:
    try:
        candidates = tty_root.iterdir()
    except OSError:
        return None
    for candidate in candidates:
        if not (candidate.name.startswith("ttyUSB") or candidate.name.startswith("ttyACM")):
            continue
        try:
            resolved = (candidate / "device").resolve()
        except OSError:
            continue
        if any(parent.name == usb_path for parent in (resolved, *resolved.parents)):
            return f"/dev/{candidate.name}"
    return None


def physical_ports(
    usb_root: Path = Path("/sys/bus/usb/devices"),
    tty_root: Path = Path("/sys/class/tty"),
    udc_root: Path = Path("/sys/class/udc"),
) -> PhysicalPortInventory:
    ports = []
    for port_id, name, label, usb_path in PORTS:
        device = usb_root / usb_path
        connected = device.exists()
        serial_device = _serial_device_for(usb_path, tty_root) if connected else None
        ports.append(
            PhysicalPort(
                id=port_id,
                name=name,
                physical_label=label,
                usb_path=usb_path,
                connected=connected,
                status="connected" if connected else "disconnected",
                device_name=_read(device / "product") if connected else None,
                vendor_id=_read(device / "idVendor") if connected else None,
                product_id=_read(device / "idProduct") if connected else None,
                serial_device=serial_device,
                console_available=port_id.startswith("console_") and serial_device is not None,
            )
        )

    try:
        udc_connected = any(udc_root.iterdir())
    except OSError:
        udc_connected = False
    ports.append(
        PhysicalPort(
            id="kvm_otg",
            name="KVM OTG",
            physical_label="USB-C SLAVE",
            connected=udc_connected,
            status="ready" if udc_connected else "setup_pending",
            device_name="HID and virtual media",
        )
    )
    return PhysicalPortInventory(ports=ports)
