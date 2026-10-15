import csv
import io

from backend.app.hardware.recovery_history import history, observe


def test_persistent_changes_and_clear(tmp_path):
    path = tmp_path / 'history.sqlite3'
    lease = dict(mac='aa:bb:cc:dd:ee:ff', ip='192.168.34.150', hostname='ilo', expires_at=123)
    observe(path, [lease], 1)
    observe(path, [lease], 2)
    assert len(history(path)) == 1
    assert history(path)[0]['observed_at'] == 1
    history(path, clear=True)
    observe(path, [lease], 3)
    assert history(path) == []
    lease['expires_at'] = 456
    observe(path, [lease], 4)
    assert history(path)[0]['expires_at'] == 456
    observe(path, [], 5)
    observe(path, [lease], 6)
    assert len(history(path)) == 2


def test_retention(tmp_path, monkeypatch):
    from backend.app.hardware import recovery_history
    monkeypatch.setattr(recovery_history, 'LIMIT', 2)
    path = tmp_path / 'history.sqlite3'
    for i in range(4):
        observe(path, [dict(mac='aa', ip='192.168.34.150', hostname=str(i))], i)
    assert [entry['hostname'] for entry in history(path)] == ['3', '2']


def test_history_api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from backend.app.api import recovery
    from backend.app.main import app
    monkeypatch.setattr(recovery, 'NETWORK_STATE', tmp_path / 'recovery-network.json')
    path = tmp_path / 'recovery-history.sqlite3'
    observe(path, [dict(mac='aa', ip='192.168.34.150', hostname='=HYPERLINK("bad"),İLO')], 1)
    client = TestClient(app)
    response = client.get('/api/v1/recovery/network/history/download')
    assert response.status_code == 200
    assert 'attachment;' in response.headers['content-disposition']
    assert 'text/csv' in response.headers['content-type']
    assert '.csv' in response.headers['content-disposition']
    rows = list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
    assert rows[0] == ['Observed (UTC)', 'Device', 'IP address', 'MAC', 'Lease expires (UTC)']
    assert rows[1][1] == "'=HYPERLINK(\"bad\"),İLO"
    assert rows[1][0] == '1970-01-01T00:00:01+00:00'
    assert rows[1][4] == 'Permanent'
    assert client.delete('/api/v1/recovery/network/history').status_code == 200
    assert client.get('/api/v1/recovery/network/history').json() == {'entries': []}
