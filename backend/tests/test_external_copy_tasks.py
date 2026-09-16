import os
import uuid

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services import external_storage, storage
from backend.app.services.tasks import task_list


def test_external_copy_uses_global_task_id_and_reports_byte_progress(tmp_path, monkeypatch):
    stage = tmp_path / "stage"
    stage.mkdir()
    source = tmp_path / "source.bin"
    payload = b"a" * (2 * 1024 * 1024 + 71)
    source.write_bytes(payload)
    monkeypatch.setattr(storage, "STORAGE_PATH", stage)
    monkeypatch.setattr(storage, "MIN_FREE_BYTES", 0)
    monkeypatch.setattr(storage, "REQUIRE_MARKER", False)
    monkeypatch.setattr(external_storage, "open_entry", lambda *args: os.open(source, os.O_RDONLY))
    snapshots = []
    update = storage._update_task

    def observe(task_id, **values):
        update(task_id, **values)
        snapshots.extend(task for task in task_list() if task["id"] == task_id)

    monkeypatch.setattr(storage, "_update_task", observe)
    task_id = str(uuid.uuid4())
    response = TestClient(app).post(
        "/api/v1/external-storage/sda1/import",
        json={"path": "folder/source.bin"},
        headers={"X-Kronos-Task-ID": task_id},
    )
    assert response.status_code == 200
    assert (stage / "source.bin").read_bytes() == payload
    assert any(0 < item["progress"] < 100 and item["bytes_done"] > 0 for item in snapshots)
    assert all(item["id"] == task_id for item in snapshots)
    task = next(item for item in task_list() if item["id"] == task_id)
    assert task["filename"] == "source.bin"
    assert task["bytes_done"] == len(payload)
    assert task["status"] == "successful"
