from types import SimpleNamespace

from backend.app.hardware import ports


def test_phone_ip_is_mapped_to_storage_port_only(tmp_path, monkeypatch):
    usb = tmp_path / "usb"
    net = tmp_path / "net"
    usb.mkdir()
    net.mkdir()
    device = usb / "1-1.1"
    interface = device / "1-1.1:1.0"
    interface.mkdir(parents=True)
    (device / "product").write_text("Galaxy")
    (net / "usb0").mkdir()
    (net / "usb0" / "device").symlink_to(interface)
    monkeypatch.setattr(ports, "external_inventory", lambda: {"devices": []})
    monkeypatch.setattr(
        ports,
        "get_network_info",
        lambda root: SimpleNamespace(
            interfaces=[SimpleNamespace(name="usb0", addresses=["10.161.147.177/24"])]
        ),
    )
    monkeypatch.setattr(
        ports.subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(stdout='[{"gateway":"10.161.147.83"}]'),
    )
    inventory = ports.physical_ports(usb, tmp_path / "tty", tmp_path / "udc", net_root=net)
    wan = next(p for p in inventory.ports if p.id == "expansion_usb")
    service = next(p for p in inventory.ports if p.id == "service_usb")
    assert wan.name == "External Storage / WAN"
    assert wan.mode == "wan"
    assert wan.status == "usb_wan_ready"
    assert wan.addresses == ["10.161.147.177/24"]
    assert wan.gateway == "10.161.147.83"
    assert service.network_interface is None
    monkeypatch.setattr(ports, "get_network_info", lambda root: SimpleNamespace(interfaces=[]))
    waiting = ports.physical_ports(usb, tmp_path / "tty", tmp_path / "udc", net_root=net)
    assert next(p for p in waiting.ports if p.id == "expansion_usb").status == "waiting_for_ip"
    (net / "usb0" / "device").unlink()
    interface.rmdir()
    (device / "product").unlink()
    device.rmdir()
    removed = ports.physical_ports(usb, tmp_path / "tty", tmp_path / "udc", net_root=net)
    wan = next(p for p in removed.ports if p.id == "expansion_usb")
    assert wan.addresses == [] and wan.mode is None and not wan.connected


def test_disk_stays_in_storage_mode(tmp_path, monkeypatch):
    (tmp_path / "2-1").mkdir()
    monkeypatch.setattr(ports, "external_inventory", lambda: {"devices": [{"status": "ready"}]})
    inventory = ports.physical_ports(
        tmp_path, tmp_path / "tty", tmp_path / "udc", net_root=tmp_path / "net"
    )
    disk = next(p for p in inventory.ports if p.id == "expansion_usb")
    assert disk.mode == "storage" and disk.status == "storage_ready"
    assert disk.addresses == [] and disk.network_interface is None
