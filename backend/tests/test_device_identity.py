from pathlib import Path

import pytest

from backend.app.services.device_identity import identity_from_serial, read_identity


def test_full_serial_and_naming_limits():
    identity = identity_from_serial("100000008ED89866\x00\n")
    assert identity == {
        "serial": "100000008ed89866", "hostname": "infrabox-8ed89866",
        "ap_ssid": "KDX-iKVM-8ed89866",
        "mdns": "infrabox-8ed89866.local",
    }
    assert len(identity["ap_ssid"].encode("ascii")) <= 32
    assert len(identity["hostname"]) <= 63
    other = identity_from_serial("000000008ed89866")
    assert other["serial"] != identity["serial"]
    assert other["ap_ssid"] == identity["ap_ssid"]


@pytest.mark.parametrize("value", ["", "0000000000000000", "ffffffffffffffff", "8ed89866",
                                   "100000008ed89z66", "100000008ed89866\nssid=shared"])
def test_invalid_serial_has_no_shared_fallback(value):
    with pytest.raises(ValueError):
        identity_from_serial(value)


def test_device_tree_and_cpuinfo_fallback(tmp_path):
    serial = tmp_path / "serial-number"
    cpu = tmp_path / "cpuinfo"
    serial.write_bytes(b"100000008ed89866\x00")
    cpu.write_text("Serial\t: 00000000deadbeef\n")
    assert read_identity([serial], cpu)["serial"] == "100000008ed89866"
    serial.unlink()
    assert read_identity([serial], cpu)["serial"] == "00000000deadbeef"
    cpu.write_text("Hardware\t: BCM2835\n")
    with pytest.raises(ValueError, match="unavailable"):
        read_identity([serial], cpu)


def test_host_and_container_start_share_generated_identity():
    script = Path("scripts/start-containers.sh").read_text()
    assert 'KRONOSKVM_HOSTNAME="$(hostname)"' in script
    assert '--hostname "${KRONOSKVM_HOSTNAME}"' in script
    boot = Path("deploy/systemd/kronoskvm-device-identity.service").read_text()
    assert "--apply --boot" in boot
