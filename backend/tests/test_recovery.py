import hashlib

import pytest
from fastapi.testclient import TestClient

from backend.app.api import recovery, services
from backend.app.main import app
from backend.app.models.storage import VirtualMediaStatus
from backend.app.services import storage

client = TestClient(app)


@pytest.fixture
def pool(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "STORAGE_PATH", tmp_path)
    monkeypatch.setattr(storage, "MIN_FREE_BYTES", 0)
    monkeypatch.setattr(storage, "REQUIRE_MARKER", False)
    monkeypatch.setattr(recovery, "virtual_media_status", lambda: VirtualMediaStatus())
    return tmp_path


def test_publish_checksum_restore_and_shared_quota(pool):
    data = b"firmware contents"
    (pool / "firmware.bin").write_bytes(data)
    original = storage.staging_info().used_bytes
    result = client.post(
        "/api/v1/recovery/files", json={"filename": "firmware.bin", "folder": "hpe"}
    )
    assert result.status_code == 201
    assert not (pool / "firmware.bin").exists()
    assert (pool / "recovery/hpe/firmware.bin").read_bytes() == data
    assert storage.staging_info().used_bytes == original
    assert storage.staging_info().files == []
    listing = client.get("/api/v1/recovery").json()["files"]
    assert listing[0]["http_url"] == "http://192.168.34.100:8080/hpe/firmware.bin"
    checksum = client.get("/api/v1/recovery/checksum/hpe/firmware.bin")
    assert checksum.json()["sha256"] == hashlib.sha256(data).hexdigest()
    assert client.post("/api/v1/recovery/restore/hpe/firmware.bin").status_code == 200
    assert (pool / "firmware.bin").read_bytes() == data
    assert storage.staging_info().used_bytes == original


@pytest.mark.parametrize("folder", ["../outside", "/tmp", "x/../y", "x//y", ".hidden", "x\\y"])
def test_publish_rejects_unsafe_paths(pool, folder):
    (pool / "firmware.bin").write_bytes(b"safe")
    assert (
        client.post(
            "/api/v1/recovery/files", json={"filename": "firmware.bin", "folder": folder}
        ).status_code
        == 400
    )
    assert (pool / "firmware.bin").read_bytes() == b"safe"


def test_publish_rejects_symlinks_duplicates_and_mounted_media(pool, monkeypatch):
    (pool / "firmware.bin").write_bytes(b"safe")
    root = recovery.recovery_root()
    (root / "outside").symlink_to(pool, target_is_directory=True)
    assert (
        client.post(
            "/api/v1/recovery/files", json={"filename": "firmware.bin", "folder": "outside"}
        ).status_code
        == 400
    )
    (root / "firmware.bin").write_bytes(b"existing")
    assert (
        client.post("/api/v1/recovery/files", json={"filename": "firmware.bin"}).status_code == 409
    )
    assert (root / "firmware.bin").read_bytes() == b"existing"
    monkeypatch.setattr(
        recovery,
        "virtual_media_status",
        lambda: VirtualMediaStatus(status="attached", filename="firmware.bin"),
    )
    assert (
        client.post(
            "/api/v1/recovery/files", json={"filename": "firmware.bin", "folder": "new"}
        ).status_code
        == 409
    )


def test_recovery_counts_against_upload_quota(pool, monkeypatch):
    root = recovery.recovery_root()
    (root / "large.bin").write_bytes(b"x" * 90)
    monkeypatch.setattr(storage, "STORAGE_CAPACITY_BYTES", 100)
    assert client.put("/api/v1/storage/files/new.bin", content=b"x" * 11).status_code == 507


def test_only_recovery_services_can_start_and_stop(pool, monkeypatch):
    monkeypatch.setattr(services, "STATE_PATH", pool)
    monkeypatch.setattr(services, "REQUEST_PATH", pool / "service-action")
    for service in ("tftp", "recovery_http", "recovery_ftp"):
        for action in ("start", "stop"):
            assert client.post(f"/api/v1/services/{service}/{action}").status_code == 202
            assert f"service={service}\naction={action}\n" in services.REQUEST_PATH.read_text()
    assert client.post("/api/v1/services/dnsmasq/stop").status_code == 400
    assert client.post("/api/v1/services/tftp/enable").status_code == 400


def test_recovery_network_missing_and_stale(pool, monkeypatch):
    import json
    import time

    target = pool / "network.json"
    monkeypatch.setattr(recovery, "NETWORK_STATE", target)
    assert client.get("/api/v1/recovery/network").json()["stale"] is True
    target.write_text(json.dumps({"updated_at": time.time(), "ports": [], "leases": []}))
    assert client.get("/api/v1/recovery/network").json()["stale"] is False
    target.write_text(json.dumps({"updated_at": 1, "ports": [], "leases": []}))
    assert client.get("/api/v1/recovery/network").json()["stale"] is True


def test_network_snapshot_filters_expired_leases_and_wifi(tmp_path):
    import importlib.util
    import time

    spec = importlib.util.spec_from_file_location(
        "snapshot", "scripts/snapshot-recovery-network.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    leases = tmp_path / "leases"
    leases.write_text(
        f"{int(time.time()) + 3600} aa:bb:cc:dd:ee:ff 192.168.34.215 ILOTEST *\n"
        "1 11:22:33:44:55:66 192.168.34.155 expired *\n"
        "broken record\n"
    )
    net = tmp_path / "net"
    for name in ("eth1", "wlan0"):
        (net / name).mkdir(parents=True)
        (net / name / "carrier").write_text("1")
        (net / "br-recovery/brif" / name).mkdir(parents=True)
    (net / "wlan0/wireless").mkdir()
    result = module.snapshot(leases, net)
    assert result["ports"] == [{"interface": "eth1", "connected": True}]
    assert [lease["ip"] for lease in result["leases"]] == ["192.168.34.215"]


def test_tasks_poll_reconciles_service_completion(pool, monkeypatch):
    import json

    from backend.app.services.tasks import start_task

    monkeypatch.setattr(services, "STATE_PATH", pool)
    task = start_task("service.start", "Start HTTP", source="services")
    (pool / f"service-result-{task['id']}.json").write_text(
        json.dumps({"successful": True, "service": "recovery_http", "action": "start"})
    )
    response = client.get("/api/v1/tasks")
    finished = next(item for item in response.json()["tasks"] if item["id"] == task["id"])
    assert finished["status"] == "successful"
    assert not (pool / f"service-result-{task['id']}.json").exists()
