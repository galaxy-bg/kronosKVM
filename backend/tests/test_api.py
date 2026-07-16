from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.hardware.serial import serial_devices
from backend.app.hardware.usb_gadget import controllers
from backend.app.hardware.video import capture_devices
from backend.app.main import create_app

client = TestClient(create_app())


def test_health() -> None:
    response = client.get("/api/v1/health", headers={"x-request-id": "test-request"})
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["version"] == "0.1.0"
    assert response.headers["x-request-id"] == "test-request"


def test_optional_hardware_does_not_block_startup() -> None:
    response = client.get("/api/v1/capabilities")
    assert response.status_code == 200
    names = {item["name"] for item in response.json()}
    assert {"video", "hid", "virtual_media", "serial", "temperature"} <= names


def test_system_endpoints() -> None:
    for path in (
        "/api/v1/system/info",
        "/api/v1/system/network",
        "/api/v1/system/storage",
        "/api/v1/system/services",
        "/api/v1/hardware/temperature",
    ):
        response = client.get(path)
        assert response.status_code == 200


def test_usb_controller_detection(tmp_path: Path) -> None:
    (tmp_path / "fe980000.usb").mkdir()
    assert controllers(tmp_path) == ["fe980000.usb"]


def test_serial_detection(tmp_path: Path) -> None:
    (tmp_path / "ttyUSB0").touch()
    (tmp_path / "ttyACM1").touch()
    assert serial_devices(tmp_path) == [
        str(tmp_path / "ttyACM1"),
        str(tmp_path / "ttyUSB0"),
    ]


def test_capture_requires_video_zero(tmp_path: Path) -> None:
    (tmp_path / "video10").touch()
    assert capture_devices(tmp_path) == []
    (tmp_path / "video0").touch()
    assert capture_devices(tmp_path) == [str(tmp_path / "video0")]
