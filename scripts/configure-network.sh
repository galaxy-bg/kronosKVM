#!/usr/bin/env bash
set -Eeuo pipefail

BACKUP_ROOT=/var/backups/kronoskvm/network
AP_ADDRESS=192.168.34.100
AP_PREFIX=24
AP_INTERFACE=wlan0
AP_SSID=kronosKVM
DRY_RUN=false

usage() {
    cat <<'EOF'
Usage: configure-network.sh [--dry-run] [--help]

Configure wlan0 as the persistent KronosKVM management access point:

  SSID:       kronosKVM
  Address:    192.168.34.100/24
  DHCP range: 192.168.34.150-192.168.34.220

The WPA passphrase is requested through a hidden interactive prompt and is
written only to root-readable hostapd configuration. It is never accepted as a
command-line argument.

Run only while an independently tested Ethernet SSH path is available.
This script does not enable routing, NAT or bridging.
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

install_content() {
    local target="$1"
    local mode="$2"
    local temporary
    temporary="$(mktemp)"
    cat >"${temporary}"
    if "${DRY_RUN}"; then
        printf '[DRY-RUN] install -m %q %q\n' "${mode}" "${target}"
    else
        install -D -m "${mode}" -o root -g root "${temporary}" "${target}"
    fi
    rm -f -- "${temporary}"
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

if [[ "$(cat /sys/class/net/eth0/carrier 2>/dev/null || true)" != "1" ]]; then
    printf '[ERROR] eth0 has no carrier; refusing to modify wlan0.\n' >&2
    exit 1
fi
for command in hostapd dnsmasq; do
    if ! command -v "${command}" >/dev/null 2>&1; then
        printf '[ERROR] Required command is missing: %s\n' "${command}" >&2
        exit 1
    fi
done

if ! "${DRY_RUN}"; then
    read -r -s -p "WPA passphrase for ${AP_SSID}: " AP_PASSPHRASE
    printf '\n'
    if (( ${#AP_PASSPHRASE} < 8 || ${#AP_PASSPHRASE} > 63 )); then
        printf '[ERROR] WPA passphrase must contain 8-63 characters.\n' >&2
        exit 1
    fi
else
    AP_PASSPHRASE=DRY_RUN_SECRET
fi

timestamp="$(date -u '+%Y%m%dT%H%M%SZ')"
backup_dir="${BACKUP_ROOT}/${timestamp}"
run install -d -m 0700 -o root -g root "${backup_dir}"

for path in \
    /etc/dhcpcd.conf \
    /etc/default/hostapd \
    /etc/hostapd/hostapd.conf \
    /etc/dnsmasq.d/kronoskvm-ap.conf; do
    if [[ -e "${path}" ]]; then
        run cp -a -- "${path}" "${backup_dir}/$(basename "${path}")"
    fi
done

if ! grep -q '^# BEGIN KRONOSKVM AP$' /etc/dhcpcd.conf; then
    if "${DRY_RUN}"; then
        printf '[DRY-RUN] append KronosKVM AP block to /etc/dhcpcd.conf\n'
    else
        cat >>/etc/dhcpcd.conf <<EOF

# BEGIN KRONOSKVM AP
interface ${AP_INTERFACE}
static ip_address=${AP_ADDRESS}/${AP_PREFIX}
nohook wpa_supplicant
# END KRONOSKVM AP
EOF
    fi
fi

install_content /etc/hostapd/hostapd.conf 0600 <<EOF
country_code=TR
interface=${AP_INTERFACE}
driver=nl80211
ssid=${AP_SSID}
hw_mode=g
channel=6
ieee80211n=1
wmm_enabled=1
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
wpa_passphrase=${AP_PASSPHRASE}
EOF

install_content /etc/default/hostapd 0644 <<'EOF'
DAEMON_CONF="/etc/hostapd/hostapd.conf"
EOF

install_content /etc/dnsmasq.d/kronoskvm-ap.conf 0644 <<EOF
interface=${AP_INTERFACE}
bind-dynamic
listen-address=${AP_ADDRESS}
dhcp-range=192.168.34.150,192.168.34.220,255.255.255.0,12h
dhcp-authoritative
domain=kronoskvm.local
local=/kronoskvm.local/
address=/kronoskvm.local/${AP_ADDRESS}
port=0
EOF

run systemctl unmask hostapd.service
run systemctl disable wpa_supplicant.service
run systemctl stop wpa_supplicant.service
run ip -4 address flush dev "${AP_INTERFACE}" scope global
run systemctl restart dhcpcd.service
run systemctl enable hostapd.service dnsmasq.service
run systemctl restart hostapd.service dnsmasq.service

if ! "${DRY_RUN}"; then
    unset AP_PASSPHRASE
    ip address show dev "${AP_INTERFACE}"
    systemctl --no-pager --full status hostapd.service dnsmasq.service
fi

printf '[INFO] AP configuration complete. Backup: %s\n' "${backup_dir}"
