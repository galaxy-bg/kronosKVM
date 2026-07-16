from pathlib import Path


def test_status_cli_is_safe_and_eth0_first() -> None:
    script = Path("scripts/kronoskvm").read_text(encoding="utf-8")
    assert "--interface eth0" in script
    assert "hostapd.service" in script
    assert "dnsmasq.service" in script
    assert "docker.service" in script
    assert "kronoskvm-containers.service" in script
    assert "wpa_passphrase" not in script
    assert "password" not in script.lower()
    assert "token" not in script.lower()


def test_cli_installer_targets_usr_local_bin() -> None:
    installer = Path("scripts/install-cli.sh").read_text(encoding="utf-8")
    assert "/usr/local/bin/kronoskvm" in installer
