import datetime as dt
import importlib.util
import json
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

from backend.app.hardware import rtc, wittypi

NOW = dt.datetime(2026, 10, 16, 1, 2, 3, tzinfo=dt.timezone.utc)


def registers():
    return {0:0x26, 12:7, 58:3, 59:2, 60:1, 61:0x16, 62:5, 63:0x10, 64:0x26}


def test_mcu_rtc_ready_without_linux_rtc_node(tmp_path, monkeypatch):
    value = wittypi.sample(registers().__getitem__, now=NOW)
    assert value['present'] and value['rtc_valid']
    assert value['rtc_time_utc'] == NOW.isoformat()
    assert value['rtc_offset_seconds'] == 0
    assert value['firmware_revision'] == '0x07'
    path = tmp_path/'wittypi-status.json'
    path.write_text(json.dumps(value))
    monkeypatch.setenv('KRONOSKVM_STATE_PATH', str(tmp_path))
    assert rtc.capability(tmp_path/'no-devices').status.value == 'ready'


@pytest.mark.parametrize('reg,value', [(58,0x83), (64,0), (59,0x7a)])
def test_invalid_clock_is_not_reported_ready(reg, value):
    data = registers()
    data[reg] = value
    result = wittypi.sample(data.__getitem__, now=NOW)
    assert result['present'] and not result['rtc_valid']


def test_unsupported_model_cannot_enable_power_handling():
    data = registers()
    data[0] = 0x37  # L3V7 charging pins conflict with this appliance keypad.
    assert not wittypi.sample(data.__getitem__, now=NOW)['present']


def test_stale_snapshot_does_not_hide_missing_rtc(tmp_path, monkeypatch):
    monkeypatch.setenv('KRONOSKVM_STATE_PATH', str(tmp_path))
    (tmp_path/'wittypi-status.json').write_text(json.dumps({
        'updated_at':time.time()-60, 'present':True, 'rtc_valid':True,
    }))
    assert rtc.capability(tmp_path).status.value == 'not_detected'


@pytest.fixture
def host():
    spec = importlib.util.spec_from_file_location('witty_host', Path('scripts/wittypi-host.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_preflight_refuses_held_button_without_rtc_writes(host, monkeypatch):
    monkeypatch.setattr(host, 'sample', lambda *a: {'present':True, 'rtc_valid':True})
    monkeypatch.setattr(host, 'command', lambda *a: '0')
    write = Mock()
    monkeypatch.setattr(host, 'write', write)
    with pytest.raises(RuntimeError, match='Release'):
        host.prepare()
    write.assert_not_called()


def test_preflight_invalid_rtc_without_ntp_never_changes_clock(host, monkeypatch):
    monkeypatch.setattr(host, 'sample', lambda *a: {'present':True, 'rtc_valid':False})
    monkeypatch.setattr(host, 'command', lambda *a: '1')
    monkeypatch.setattr(host, 'synchronized', lambda: False)
    write = Mock()
    monkeypatch.setattr(host, 'write', write)
    with pytest.raises(RuntimeError, match='NTP unavailable'):
        host.prepare()
    write.assert_not_called()


def test_preflight_preserves_saved_alarms(host, monkeypatch):
    monkeypatch.setattr(host, 'sample', lambda *a: {'present':True, 'rtc_valid':False})
    monkeypatch.setattr(host, 'command', lambda *a: '1')
    monkeypatch.setattr(host, 'synchronized', lambda: True)
    monkeypatch.setattr(host, 'read', lambda *a: 5)
    write = Mock()
    monkeypatch.setattr(host, 'write', write)
    with pytest.raises(RuntimeError, match='saved alarms'):
        host.prepare()
    write.assert_not_called()


def test_preflight_refuses_uart_low_without_writes(host, monkeypatch):
    monkeypatch.setattr(host, 'sample', lambda *a: {'present':True, 'rtc_valid':True})
    monkeypatch.setattr(host, 'command', lambda args: '0' if args[-1] == '14' else '1')
    write = Mock()
    monkeypatch.setattr(host, 'write', write)
    with pytest.raises(RuntimeError, match='UART TXD'):
        host.prepare()
    write.assert_not_called()


def test_preflight_writes_only_rtc_calendar_in_utc(host, monkeypatch):
    values = iter([{'present':True, 'rtc_valid':False},
                   {'present':True, 'rtc_valid':True, 'rtc_offset_seconds':0}])
    monkeypatch.setattr(host, 'sample', lambda *a: next(values))
    monkeypatch.setattr(host, 'command', lambda *a: '1')
    monkeypatch.setattr(host, 'synchronized', lambda: True)
    monkeypatch.setattr(host, 'read', lambda *a: 0)
    writes = []
    monkeypatch.setattr(host, 'write', lambda reg, value: writes.append((reg,value)))
    host.prepare()
    assert {reg for reg,value in writes} == set(range(58,65))
    assert writes[-1][0] == 58
    assert all(0 <= value <= 0x99 for reg,value in writes)


def test_host_helper_imports_without_application_site_packages():
    import subprocess
    import sys

    result = subprocess.run([sys.executable, '-S', '-c',
                             'import runpy; runpy.run_path("scripts/wittypi-host.py")'],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_services_shows_real_witty_rtc_and_service_state(monkeypatch):
    from backend.app.api import services

    monkeypatch.setattr(services, '_read_status', lambda: {
        'services':{'wittypi':{'state':'active', 'detail':'wittypi.service'}}})
    monkeypatch.setattr(services, 'wittypi_snapshot', lambda: wittypi.sample(
        registers().__getitem__, now=NOW))
    card = next(item for item in services.service_list()['services'] if item['id']=='wittypi')
    assert card['state'] == 'active'
    assert 'firmware 0x07' in card['detail']
    assert NOW.isoformat() in card['detail']
