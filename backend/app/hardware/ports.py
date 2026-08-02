from pathlib import Path
from typing import Optional

from backend.app.models import PhysicalPort, PhysicalPortInventory

PORTS = (
    ("console_1", "Console 1", "USB-A 2.0 · Console 1", ("1-1.3",)),
    ("console_2", "Console 2", "USB-A 2.0 · Console 2", ("1-1.4",)),
    ("service_usb", "Service USB", "USB-A 3.0 · Service", ("1-1.1", "2-1")),
    ("expansion_usb", "External Storage", "USB-A 3.0 · Storage", ("1-1.2", "2-2")),
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
    video_device: Path = Path("/dev/video0"),
) -> PhysicalPortInventory:
    ports = []
    for port_id, name, label, usb_paths in PORTS:
        active_path = next((path for path in usb_paths if (usb_root / path).exists()), None)
        device = usb_root / active_path if active_path else None
        connected = device is not None
        serial_device = _serial_device_for(active_path, tty_root) if active_path else None
        ports.append(
            PhysicalPort(
                id=port_id,
                name=name,
                physical_label=label,
                usb_path=" / ".join(usb_paths),
                connected=connected,
                status="connected" if connected else "disconnected",
                device_name=_read(device / "product") if device else None,
                vendor_id=_read(device / "idVendor") if device else None,
                product_id=_read(device / "idProduct") if device else None,
                serial_device=serial_device,
                console_available=port_id.startswith("console_") and serial_device is not None,
            )
        )

    ports.append(
        PhysicalPort(
            id="video_capture",
            name="Video Input",
            physical_label="HDMI → capture → CSI-2",
            usb_path="/dev/video0",
            connected=video_device.exists(),
            status="ready" if video_device.exists() else "not_detected",
            device_name="TC358743 HDMI capture" if video_device.exists() else None,
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
            physical_label="USB-C OTG · Device",
            connected=udc_connected,
            status="ready" if udc_connected else "waiting_for_gpio_power",
            device_name=(
                "HID and virtual media"
                if udc_connected
                else "USB-C currently used for appliance power"
            ),
        )
    )
    return PhysicalPortInventory(ports=ports)
