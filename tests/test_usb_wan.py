import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('usb_wan', Path('scripts/check-usb-wan.py'))
usb_wan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(usb_wan)


def test_phone_detection_uses_driver_and_physical_port(tmp_path):
    net = tmp_path / 'net'
    net.mkdir()
    for name, port, driver in [('eth0', 'pci', 'bcmgenet'),
                               ('eth1', '1-1.1', 'ipheth'),
                               ('usb0', '1-1.2', 'rndis_host'),
                               ('eth2', '2-1', 'cdc_ncm')]:
        device = tmp_path / 'devices' / port / f'{port}:1.0'
        device.mkdir(parents=True)
        driver_path = tmp_path / 'drivers' / driver
        driver_path.mkdir(parents=True, exist_ok=True)
        (device / 'driver').symlink_to(driver_path)
        (net / name).mkdir()
        (net / name / 'device').symlink_to(device)
    interfaces = {item['interface']: item for item in usb_wan.phone_interfaces(net)}
    assert 'eth0' not in interfaces
    assert interfaces['eth1']['storage_port'] is True
    assert interfaces['eth2']['storage_port'] is True
    assert interfaces['usb0']['storage_port'] is False


def test_probe_binds_usb_and_never_probes_service_port(monkeypatch):
    monkeypatch.setattr(usb_wan, 'phone_interfaces', lambda: [
        {'interface': 'usb0', 'storage_port': True},
        {'interface': 'eth1', 'storage_port': False},
    ])
    calls = []
    monkeypatch.setattr(usb_wan, 'command', lambda args: calls.append(args) or {'ok': True})
    usb_wan.check(probe=True)
    probes = [args for args in calls if args[0] == 'curl']
    assert len(probes) == 1
    assert probes[0][probes[0].index('--interface') + 1] == 'usb0'
    assert probes[0][probes[0].index('--noproxy') + 1] == '*'
