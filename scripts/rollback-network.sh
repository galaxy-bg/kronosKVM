#!/usr/bin/env bash
set -Eeuo pipefail

BACKUP_ROOT=/var/backups/kronoskvm/network
DRY_RUN=false

usage() {
    cat <<'EOF'
Usage: rollback-network.sh [--dry-run] [--help]

Disable the KronosKVM AP, remove its managed dhcpcd block and restore the most
recent backed-up network files when available. Re-enable wlan0 client mode.
EOF
}

run() {
    if "${DRY_RUN}"; then
        printf '[DRY-RUN]'
        printf ' %q' "$@"
        printf '\n'
    else
        "$@"
    fi
}

while (( $# > 0 )); do
    case "$1" in
        --dry-run) DRY_RUN=true ;;
        --help|-h) usage; exit 0 ;;
        *) printf '[ERROR] Unknown argument: %s\n' "$1" >&2; exit 2 ;;
    esac
    shift
done

if (( EUID != 0 )); then
    printf '[ERROR] Run as root.\n' >&2
    exit 1
fi

run systemctl disable --now hostapd.service dnsmasq.service

if "${DRY_RUN}"; then
    printf '[DRY-RUN] remove KronosKVM AP block from /etc/dhcpcd.conf\n'
else
    sed -i '/^# BEGIN KRONOSKVM AP$/,/^# END KRONOSKVM AP$/d' /etc/dhcpcd.conf
    rm -f -- /etc/dnsmasq.d/kronoskvm-ap.conf
fi

run systemctl enable wpa_supplicant.service
run systemctl restart dhcpcd.service
run systemctl restart wpa_supplicant.service

printf '[INFO] AP disabled; wlan0 client mode requested.\n'
