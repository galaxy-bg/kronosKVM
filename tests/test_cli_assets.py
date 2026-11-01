import os
import subprocess
from pathlib import Path

import pytest


def test_status_cli_is_safe() -> None:
    script = Path("scripts/kronoskvm").read_text(encoding="utf-8")
    assert "hostapd.service" in script
    assert "dnsmasq.service" in script
    assert "docker.service" in script
    assert "kronoskvm-containers.service" in script
    assert "wpa_passphrase" not in script
    assert "password" not in script.lower()
    assert "token" not in script.lower()


@pytest.mark.parametrize(
    ("route", "curl_status", "expected"),
    [
        ("1.1.1.1 via 192.168.1.1 dev eth0 src 192.168.1.2", "0", "reachable via eth0"),
        ("1.1.1.1 via 10.107.147.224 dev usb0 src 10.107.147.39", "0", "reachable via usb0"),
        ("1.1.1.1 via 10.107.147.224 dev usb0 src 10.107.147.39", "1", "unreachable via usb0"),
        ("", "0", "unreachable (no IPv4 route)"),
    ],
)
def test_internet_probe_uses_selected_uplink(route, curl_status, expected):
    script = Path("scripts/kronoskvm").read_text(encoding="utf-8")
    function = script.split("internet_state() {", 1)[1].split("\n}\n", 1)[0]
    function = "internet_state() {" + function.replace("/usr/sbin/ip", "mock_ip") + "\n}"
    harness = '''
set -Eeuo pipefail
mock_ip() {
    [[ -n "$TEST_ROUTE" ]] || return 2
    printf '%s\\n' "$TEST_ROUTE"
}
curl() {
    local arg previous=''
    for arg in "$@"; do
        if [[ "$previous" == '--interface' ]]; then
            printf 'bound:%s\\n' "$arg" >&2
        fi
        previous="$arg"
    done
    return "$TEST_CURL_STATUS"
}
'''
    result = subprocess.run(
        ["bash", "-c", harness + function + "\ninternet_state"],
        env={**os.environ, "TEST_ROUTE": route, "TEST_CURL_STATUS": curl_status},
        capture_output=True, text=True, check=True,
    )
    assert result.stdout.strip() == expected
    if route:
        interface = route.split(" dev ")[1].split()[0]
        assert result.stderr.strip() == f"bound:{interface}"
    else:
        assert result.stderr == ""


def test_cli_installer_targets_usr_local_bin() -> None:
    installer = Path("scripts/install-cli.sh").read_text(encoding="utf-8")
    assert "/usr/local/bin/kronoskvm" in installer
