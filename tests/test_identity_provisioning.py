import importlib.util
from types import SimpleNamespace

import pytest

from backend.app.services.device_identity import identity_from_serial


@pytest.fixture
def provision(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("identity_host", "scripts/device-identity.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "SYSTEM_ROOT", tmp_path)
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)
    monkeypatch.setattr(module, "ap_profile", lambda: "ap-uuid")
    files = {"etc/hosts": "127.0.0.1 localhost\n127.0.1.1 old-name\n",
             "etc/dnsmasq.d/kronoskvm-ap.conf": "domain=kdx-infrabox.local\n",
             "opt/kronoskvm/.env": "OTHER_SETTING=preserve\n",
             "sys/class/net/eth0/carrier": "1\n",
             "etc/kronoskvm/tls/cert": "existing certificate"}
    for name, value in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)
    commands = []

    def run(args, required=True):
        commands.append(args)
        value = "old-name" if args == ["hostname"] else "old-ssid"
        return SimpleNamespace(stdout=value, returncode=0)

    monkeypatch.setattr(module, "run", run)
    return module, tmp_path, commands, files


def test_dry_run_never_mutates_identity(provision):
    module, root, commands, files = provision
    module.apply(identity_from_serial("100000008ed89866"), network=True, dry_run=True)
    assert all((root / name).read_text() == value for name, value in files.items())
    assert not (root / "var/backups").exists()
    assert not any(args[0] in {"hostnamectl", "systemctl"} for args in commands)


def test_migration_preserves_other_settings_and_only_reconnects_ap(provision):
    module, root, commands, files = provision
    module.apply(identity_from_serial("100000008ed89866"), network=True)
    assert "127.0.1.1 infrabox-8ed89866" in (root / "etc/hosts").read_text()
    assert "OTHER_SETTING=preserve" in (root / "opt/kronoskvm/.env").read_text()
    assert "KRONOSKVM_HOSTNAME=infrabox-8ed89866" in (
        root / "opt/kronoskvm/.env").read_text()
    assert ["nmcli", "connection", "up", "uuid", "ap-uuid"] in commands
    assert not any("eth0" in args for args in commands)
    assert (root / "etc/kronoskvm/tls/cert").read_text() == files["etc/kronoskvm/tls/cert"]


def test_failed_ap_activation_restores_files_and_names(provision, monkeypatch):
    module, root, commands, files = provision
    original = module.run

    def fail_once(args, required=True):
        if args == ["nmcli", "connection", "up", "uuid", "ap-uuid"] and required:
            raise RuntimeError("Activation failed")
        return original(args, required)

    monkeypatch.setattr(module, "run", fail_once)
    with pytest.raises(RuntimeError, match="Activation failed"):
        module.apply(identity_from_serial("100000008ed89866"), network=True)
    assert all((root / name).read_text() == value for name, value in files.items())
    assert not (root / "etc/kronoskvm/device-identity.json").exists()
    assert ["hostnamectl", "set-hostname", "old-name"] in commands
    assert ["nmcli", "connection", "modify", "uuid", "ap-uuid",
            "802-11-wireless.ssid", "old-ssid"] in commands


def test_boot_can_generate_identity_without_ethernet(provision):
    module, root, _, _ = provision
    (root / "sys/class/net/eth0/carrier").write_text("0\n")
    module.apply(identity_from_serial("100000008ed89866"), network=True, boot=True)
    assert "100000008ed89866" in (root / "etc/kronoskvm/device-identity.json").read_text()
