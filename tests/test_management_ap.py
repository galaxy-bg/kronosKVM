import subprocess
from pathlib import Path

import pytest

HELPER = Path(__file__).resolve().parents[1] / "scripts" / "management-ap.sh"


@pytest.mark.parametrize(
    ("active", "profiles", "command", "expected", "success"),
    [
        ("renamed", "renamed other", "active_management_ap_uuid", "renamed", True),
        ("--", "renamed", "management_ap_uuid", "renamed", True),
        ("station", "station renamed", "active_management_ap_uuid", "", False),
        ("station", "station renamed", "management_ap_uuid", "renamed", True),
        ("--", "renamed other", "management_ap_uuid", "", False),
        ("--", "station", "management_ap_uuid", "", False),
    ],
)
def test_management_ap_resolution(active, profiles, command, expected, success):
    # Stub only NetworkManager responses; exercise the actual shell resolver.
    mock = r'''
nmcli() {
    case "$2" in
        GENERAL.CON-UUID) printf '%s\n' "$active" ;;
        UUID) for profile in $profiles; do printf '%s\n' "$profile"; done ;;
        connection.interface-name) printf 'wlan0\n' ;;
        802-11-wireless.mode)
            if [[ "$6" == station ]]; then printf 'infrastructure\n'; else printf 'ap\n'; fi ;;
        *) return 1 ;;
    esac
}
'''
    result = subprocess.run(
        ["bash", "-c", 'source "$1"; active="$2"; profiles="$3"; ' + mock + command,
         "test", str(HELPER), active, profiles],
        capture_output=True,
        text=True,
    )
    assert (result.returncode == 0) == success
    assert result.stdout == expected
