import hashlib

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services import checksum, storage


@pytest.fixture
def pool(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'STORAGE_PATH', tmp_path)
    monkeypatch.setattr(storage, 'REQUIRE_MARKER', False)
    return tmp_path


@pytest.mark.parametrize('data', [b'', b'abc', b'iso' * 1600000])
def test_checksum_matches_reference(pool, data):
    (pool / 'image.iso').write_bytes(data)
    result = TestClient(app).post('/api/v1/storage/checksum/image.iso')
    assert result.status_code == 200
    assert result.json()['sha256'] == hashlib.sha256(data).hexdigest()
    assert result.json()['size_bytes'] == len(data)


def test_checksum_rejects_symlink_and_busy(pool):
    (pool / 'image.iso').write_bytes(b'iso')
    (pool / 'link.iso').symlink_to(pool / 'image.iso')
    client = TestClient(app)
    assert client.post('/api/v1/storage/checksum/link.iso').status_code == 404
    with checksum.HASH_LOCK:
        assert client.post('/api/v1/storage/checksum/image.iso').status_code == 409


def test_checksum_rejects_replaced_file(pool, monkeypatch):
    path = pool / 'image.iso'
    path.write_bytes(b'original')
    def change_file(task_id, **values):
        if values.get('bytes_done', 0):
            replacement = pool / 'replacement'
            replacement.write_bytes(b'changed')
            replacement.replace(path)
    monkeypatch.setattr(checksum, 'update_task', change_file)
    assert TestClient(app).post('/api/v1/storage/checksum/image.iso').status_code == 409
    assert not checksum.HASH_LOCK.locked()
