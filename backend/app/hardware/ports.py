import json
import subprocess
from pathlib import Path
from typing import Optional

from backend.app.models import PhysicalPort, PhysicalPortInventory
from backend.app.services.external_storage import inventory as external_inventory
from backend.app.services.system import get_network_info

PORTS = (
    ("console_1", "Console 1", "USB-A 2.0 · Console 1", ("1-1.3",)),
    ("console_2", "Console 2", "USB-A 2.0 · Console 2", ("1-1.4",)),
    ("expansion_usb", "External Storage / WAN", "USB-A 3.0 · Storage / WAN", ("1-1.1", "2-1")),
    ("service_usb", "Service USB", "USB-A 3.0 · Service", ("1-1.2", "2-2")),
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


def _network_for(usb_path: str, net_root: Path) -> dict:
    try:
        candidates = sorted(net_root.iterdir())
    except OSError:
        return {}
    for candidate in candidates:
        device = (candidate / "device").resolve()
        if not any(parent.name == usb_path for parent in (device, *device.parents)):
            continue
        addresses = next(
            (
                item.addresses
                for item in get_network_info(net_root).interfaces
                if item.name == candidate.name
            ),
            [],
        )
        gateway = None
        try:
            result = subprocess.run(
                ["/usr/sbin/ip", "-j", "-4", "route", "show", "default", "dev", candidate.name],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            routes = json.loads(result.stdout)
            gateway = next((route["gateway"] for route in routes if "gateway" in route), None)
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
        return {"network_interface": candidate.name, "addresses": addresses, "gateway": gateway}
    return {}


def physical_ports(
    usb_root: Path = Path("/sys/bus/usb/devices"),
    tty_root: Path = Path("/sys/class/tty"),
    udc_root: Path = Path("/sys/class/udc"),
    video_device: Path = Path("/dev/video0"),
    net_root: Path = Path("/sys/class/net"),
) -> PhysicalPortInventory:
    ports = []
    external_ready = any(item["status"] == "ready" for item in external_inventory()["devices"])
    for port_id, name, label, usb_paths in PORTS:
        active_path = next((path for path in usb_paths if (usb_root / path).exists()), None)
        device = usb_root / active_path if active_path else None
        connected = device is not None
        serial_device = _serial_device_for(active_path, tty_root) if active_path else None
        network = _network_for(active_path, net_root) if active_path else {}
        mode = None
        port_status = "connected" if connected else "disconnected"
        if port_id == "expansion_usb":
            if network:
                mode = "wan"
                port_status = (
                    "usb_wan_ready"
                    if any(":" not in address for address in network["addresses"])
                    else "waiting_for_ip"
                )
            elif connected:
                storage_class = any(
                    _read(path / "bInterfaceClass") == "08"
                    for path in usb_root.glob(f"{active_path}:*")
                )
                mode = "storage" if external_ready or storage_class else "unknown"
                port_status = "storage_ready" if external_ready else "connected"
        ports.append(
            PhysicalPort(
                id=port_id,
                name=name,
                physical_label=label,
                usb_path=" / ".join(usb_paths),
                connected=connected,
                status=port_status,
                mode=mode,
                **network,
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
