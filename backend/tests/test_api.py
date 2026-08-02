from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.hardware.serial import serial_devices
from backend.app.hardware.usb_gadget import controllers
from backend.app.hardware.video import capture_devices
from backend.app.main import create_app
from backend.app.services import connections as connection_service
from backend.app.services import storage as storage_service
from backend.app.services import virtual_media as virtual_media_service

client = TestClient(create_app())


def test_health() -> None:
    response = client.get("/api/v1/health", headers={"x-request-id": "test-request"})
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["version"] == "0.1.0"
    assert response.headers["x-request-id"] == "test-request"


def test_mutations_create_logged_tasks() -> None:
    from backend.app.services import tasks as task_service

    task_service.TASKS.clear()
    response = client.post(
        "/api/v1/system/power",
        json={"action": "reboot", "confirmed": False},
    )
    assert response.status_code == 400
    task_id = response.headers["x-kronos-task-id"]
    task = next(
        item
        for item in client.get("/api/v1/tasks").json()["tasks"]
        if item["id"] == task_id
    )
    assert task["status"] == "failed"
    assert task["error"] == "HTTP 400"


def test_network_settings_lists_ethernet_and_stages_static_request(
    tmp_path: Path, monkeypatch
) -> None:
    from backend.app.api import network_settings

    net_root = tmp_path / "net"
    state = tmp_path / "state"
    eth0 = net_root / "eth0"
    eth0.mkdir(parents=True)
    (eth0 / "device").mkdir()
    state.mkdir()
    monkeypatch.setattr(network_settings, "NET_ROOT", net_root)
    monkeypatch.setattr(network_settings, "STATE_PATH", state)
    monkeypatch.setattr(network_settings, "REQUEST_PATH", state / "network-action")

    listing = client.get("/api/v1/network/settings")
    assert listing.status_code == 200
    assert listing.json()["interfaces"][0]["interface"] == "eth0"

    response = client.post(
        "/api/v1/network/settings",
        json={
            "interface": "eth0",
            "mode": "static",
            "address": "192.168.50.10/24",
            "gateway": "192.168.50.1",
            "dns": ["1.1.1.1", "8.8.8.8"],
            "confirmed": True,
        },
    )
    assert response.status_code == 202
    request = network_settings.REQUEST_PATH.read_text(encoding="ascii")
    assert "interface=eth0" in request
    assert "address=192.168.50.10/24" in request
    assert "dns=1.1.1.1,8.8.8.8" in request


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
        "/api/v1/hardware/ports",
    ):
        response = client.get(path)
        assert response.status_code == 200


def test_power_action_requires_confirmation_and_stages_request(
    tmp_path: Path, monkeypatch
) -> None:
    from backend.app.api import routes

    action_path = tmp_path / "power-action"
    monkeypatch.setattr(routes, "POWER_ACTION_PATH", action_path)
    denied = client.post(
        "/api/v1/system/power",
        json={"action": "reboot", "confirmed": False},
    )
    assert denied.status_code == 400
    accepted = client.post(
        "/api/v1/system/power",
        json={"action": "reboot", "confirmed": True},
    )
    assert accepted.status_code == 202
    assert action_path.read_text(encoding="ascii") == "reboot\n"


def test_physical_port_detection(tmp_path: Path) -> None:
    from backend.app.hardware.ports import physical_ports

    usb_root = tmp_path / "usb"
    tty_root = tmp_path / "tty"
    udc_root = tmp_path / "udc"
    usb_root.mkdir()
    tty_root.mkdir()
    udc_root.mkdir()
    device = usb_root / "1-1.3"
    device.mkdir()
    (device / "product").write_text("USB Serial Adapter", encoding="utf-8")
    inventory = physical_ports(usb_root, tty_root, udc_root)
    console_1 = next(port for port in inventory.ports if port.id == "console_1")
    assert console_1.connected is True
    assert console_1.device_name == "USB Serial Adapter"


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


def test_staging_storage_file_lifecycle(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(storage_service, "STORAGE_PATH", tmp_path / "staging")
    monkeypatch.setattr(storage_service, "REQUIRE_MARKER", True)
    storage_service.STORAGE_PATH.mkdir()
    (storage_service.STORAGE_PATH / storage_service.MEDIA_MARKER).touch()
    payload = b"KronosKVM firmware test"
    upload = client.put("/api/v1/storage/files/switch-fw.bin", content=payload)
    assert upload.status_code == 200
    assert upload.json()["size_bytes"] == len(payload)
    listing = client.get("/api/v1/storage")
    assert listing.status_code == 200
    assert listing.json()["files"][0]["name"] == "switch-fw.bin"
    download = client.get("/api/v1/storage/files/switch-fw.bin")
    assert download.content == payload
    assert client.delete("/api/v1/storage/files/switch-fw.bin").status_code == 200
    assert client.get("/api/v1/storage").json()["file_count"] == 0


def test_staging_storage_rejects_unsafe_names() -> None:
    from backend.app.services.storage import _safe_name

    for name in ("../firmware.bin", ".hidden", "folder/file.iso", "folder\\file.iso"):
        try:
            _safe_name(name)
        except Exception as error:
            assert getattr(error, "status_code", None) == 400
        else:
            raise AssertionError(f"Unsafe name accepted: {name}")


def test_incomplete_storage_uploads_are_cleaned(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(storage_service, "STORAGE_PATH", tmp_path)
    monkeypatch.setattr(storage_service, "REQUIRE_MARKER", False)
    fragment = tmp_path / ".installer.iso.test-task.uploading"
    completed = tmp_path / "firmware.bin"
    fragment.write_bytes(b"partial")
    completed.write_bytes(b"complete")
    assert storage_service.cleanup_incomplete_uploads() == [fragment.name]
    assert not fragment.exists()
    assert completed.exists()


def test_staging_storage_requires_initialized_media(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(storage_service, "STORAGE_PATH", tmp_path / "external")
    monkeypatch.setattr(storage_service, "REQUIRE_MARKER", True)
    response = client.get("/api/v1/storage")
    assert response.status_code == 200
    assert response.json()["status"] == "media_missing"
    assert client.put("/api/v1/storage/files/test.iso", content=b"data").status_code == 503


def test_virtual_media_attach_and_eject_requests(tmp_path: Path, monkeypatch) -> None:
    staging = tmp_path / "storage"
    state = tmp_path / "state"
    staging.mkdir()
    state.mkdir()
    (staging / "linux.iso").write_bytes(b"iso")
    monkeypatch.setattr(storage_service, "STORAGE_PATH", staging)
    monkeypatch.setattr(storage_service, "REQUIRE_MARKER", False)
    monkeypatch.setattr(virtual_media_service, "STATE_PATH", state)
    monkeypatch.setattr(virtual_media_service, "REQUEST_PATH", state / "virtual-media-action")
    monkeypatch.setattr(virtual_media_service, "STATUS_PATH", state / "virtual-media-status")

    attached = client.post("/api/v1/storage/virtual-media", json={"filename": "linux.iso"})
    assert attached.status_code == 202
    assert attached.json()["status"] == "attaching"
    assert virtual_media_service.REQUEST_PATH.read_text(encoding="utf-8") == "attach\nlinux.iso\n"

    ejected = client.delete("/api/v1/storage/virtual-media")
    assert ejected.status_code == 202
    assert ejected.json()["status"] == "ejecting"
    assert virtual_media_service.REQUEST_PATH.read_text(encoding="utf-8") == "eject\n\n"


def test_virtual_media_rejects_non_image(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(storage_service, "STORAGE_PATH", tmp_path)
    monkeypatch.setattr(storage_service, "REQUIRE_MARKER", False)
    (tmp_path / "firmware.bin").write_bytes(b"firmware")
    response = client.post(
        "/api/v1/storage/virtual-media",
        json={"filename": "firmware.bin"},
    )
    assert response.status_code == 400


def test_connection_profile_lifecycle(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(connection_service, "STATE_PATH", tmp_path)
    monkeypatch.setattr(connection_service, "CONNECTIONS_FILE", tmp_path / "connections.json")
    payload = {
        "name": "Core switch",
        "type": "ssh",
        "host": "192.168.10.2",
        "port": 22,
        "username": "admin",
        "path": "/",
    }
    created = client.post("/api/v1/connections", json=payload)
    assert created.status_code == 201
    profile_id = created.json()["id"]
    assert client.get("/api/v1/connections").json()[0]["name"] == "Core switch"
    payload["name"] = "Core switch updated"
    assert client.put(f"/api/v1/connections/{profile_id}", json=payload).status_code == 200
    assert client.delete(f"/api/v1/connections/{profile_id}").status_code == 204
    assert client.get("/api/v1/connections").json() == []
