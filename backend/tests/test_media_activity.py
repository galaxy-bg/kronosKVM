import importlib.util
import json
from pathlib import Path

from backend.app.services import virtual_media

spec = importlib.util.spec_from_file_location(
    'activity', Path(__file__).resolve().parents[2] / 'scripts/snapshot-media-activity.py')
activity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(activity)


def test_activity_tracks_cached_reads_idle_disconnect_and_reset(tmp_path):
    proc, lun, udc = [tmp_path / name for name in ('proc', 'lun', 'udc')]
    (proc / '12').mkdir(parents=True)
    lun.mkdir()
    (udc / 'usb').mkdir(parents=True)
    (proc / '12/comm').write_text('file-storage\n')
    counter = proc / '12/io'
    counter.write_text('rchar: 100\nread_bytes: 0\n')
    (lun / 'file').write_text('/storage/ubuntu.iso\n')
    (udc / 'usb/state').write_text('configured')
    status = tmp_path / 'status'
    status.write_text('attached')
    def sample(previous, now):
        return activity.snapshot(previous, proc, lun, udc, status, now)
    initial = sample({}, 100)
    assert initial['state'] == 'unknown'
    counter.write_text('rchar: 1100\nread_bytes: 0\n')
    reading = sample(initial, 105)
    assert reading['state'] == 'reading'
    assert reading['read_bytes_per_second'] == 200
    assert reading['observed_bytes'] == 1000
    idle = sample(reading, 110)
    assert idle['state'] == 'idle'
    assert idle['last_read_at'] == 105
    (udc / 'usb/state').write_text('not attached')
    assert sample(idle, 115)['state'] == 'disconnected'
    (udc / 'usb/state').write_text('configured')
    counter.write_text('rchar: 0\n')
    assert sample(idle, 115)['state'] == 'unknown'
    assert sample(idle, 150)['state'] == 'unknown'
    (lun / 'file').write_text('\n')
    assert sample(idle, 115)['state'] == 'ejected'


def test_api_rejects_stale_or_wrong_image(tmp_path, monkeypatch):
    monkeypatch.setattr(virtual_media, 'STATE_PATH', tmp_path)
    monkeypatch.setattr(virtual_media.time, 'time', lambda: 100)
    target = tmp_path / 'media-activity.json'
    assert virtual_media.media_activity('ubuntu.iso')['state'] == 'unknown'
    target.write_text(json.dumps(dict(updated_at=95, filename='ubuntu.iso', state='reading')))
    assert virtual_media.media_activity('ubuntu.iso')['state'] == 'reading'
    assert virtual_media.media_activity('other.iso')['state'] == 'unknown'
    target.write_text(json.dumps(dict(updated_at=1, filename='ubuntu.iso', state='reading')))
    assert virtual_media.media_activity('ubuntu.iso')['state'] == 'unknown'


def test_force_eject_is_explicit_and_normal_eject_remains_default(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from backend.app.main import app

    monkeypatch.setattr(virtual_media, 'STATE_PATH', tmp_path)
    monkeypatch.setattr(virtual_media, 'REQUEST_PATH', tmp_path / 'virtual-media-action')
    client = TestClient(app)
    assert client.delete('/api/v1/storage/virtual-media').status_code == 202
    assert virtual_media.REQUEST_PATH.read_text().splitlines()[0] == 'eject'
    assert client.delete('/api/v1/storage/virtual-media?force=true').status_code == 202
    assert virtual_media.REQUEST_PATH.read_text().splitlines()[0] == 'force_eject'
