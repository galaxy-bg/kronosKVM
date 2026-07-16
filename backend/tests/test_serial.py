from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.hardware.serial import discover_devices
from backend.app.main import create_app
from backend.app.services.serial import SerialLockRegistry, load_profiles


def test_discovery_returns_usb_metadata(tmp_path: Path) -> None:
    device_root = tmp_path / "dev"
    serial_root = device_root / "serial"
    sys_root = tmp_path / "sys" / "class" / "tty"
    usb_root = tmp_path / "sys" / "devices" / "usb1" / "1-1"
    device_root.mkdir(parents=True)
    (serial_root / "by-id").mkdir(parents=True)
    (sys_root / "ttyUSB0").mkdir(parents=True)
    usb_root.mkdir(parents=True)

    device = device_root / "ttyUSB0"
    device.touch()
    (usb_root / "idVendor").write_text("0403\n", encoding="utf-8")
    (usb_root / "idProduct").write_text("6001\n", encoding="utf-8")
    (usb_root / "serial").write_text("adapter-1\n", encoding="utf-8")
    (sys_root / "ttyUSB0" / "device").symlink_to(usb_root)
    (serial_root / "by-id" / "usb-adapter").symlink_to(device)

    devices = discover_devices(device_root, serial_root, sys_root)
    assert len(devices) == 1
    assert devices[0].vendor_id == "0403"
    assert devices[0].product_id == "6001"
    assert devices[0].serial_number == "adapter-1"
    assert devices[0].stable_path.endswith("usb-adapter")


def test_profiles_have_safe_defaults(tmp_path: Path) -> None:
    profiles = load_profiles(tmp_path / "missing.yaml")
    default = next(profile for profile in profiles if profile.name == "default")
    assert default.baud_rate == 9600
    assert default.data_bits == 8
    assert default.parity == "none"
    assert default.stop_bits == 1


def test_serial_lock_is_exclusive() -> None:
    registry = SerialLockRegistry()
    first = registry.acquire("/dev/ttyUSB0", "operator-a")
    assert first is not None
    assert registry.acquire("/dev/ttyUSB0", "operator-b") is None
    assert registry.release("/dev/ttyUSB0", "wrong-token") is False
    assert registry.release("/dev/ttyUSB0", first.token) is True


def test_serial_api_reports_no_devices() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/serial/devices")
    assert response.status_code == 200
    assert response.json()["tcp_exposure_enabled"] is False
    assert response.json()["profiles"]


def test_lock_rejects_unknown_device() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/serial/locks",
        json={"device": "/dev/ttyUSB999", "owner": "test"},
    )
    assert response.status_code == 404
