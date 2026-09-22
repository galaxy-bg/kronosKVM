#!/usr/bin/env bash
# Pi 4 Storage/WAN host port; leaves Ethernet and recovery AP active.
set -Eeuo pipefail
[[ ${EUID} -eq 0 ]] || { echo 'Run as root' >&2; exit 1; }
export PATH="/usr/sbin:/usr/bin:/sbin:/bin"
command -v nmcli >/dev/null
[[ -d /sys/bus/usb/devices/1-1 ]] || { echo 'Expected Pi 4 USB hub missing' >&2; exit 1; }
controller_path="$(udevadm info -q property -p /sys/bus/usb/devices/1-1 | sed -n 's/^ID_PATH=//p')"
[[ "$controller_path" == *-usb-0:1 ]] || { echo 'Unexpected USB topology' >&2; exit 1; }
controller_path="${controller_path%-usb-0:1}"
backup="/var/backups/kronoskvm/usb-wan/$(date -u +%Y%m%dT%H%M%SZ)"
install -d -m 0700 "$backup"
cp -a /etc/NetworkManager/system-connections "$backup/"
nmcli -t -f NAME,UUID,TYPE connection show > "$backup/profiles.txt"

for module in rndis_host cdc_ether cdc_ncm ipheth; do modprobe "$module"; done
# iPhone requires userspace pairing as well as the ipheth kernel driver.
missing=false
for package in usbmuxd libimobiledevice-utils ipheth-utils; do
    [[ "$(dpkg-query -W -f='${Status}' "$package" 2>/dev/null || true)" == 'install ok installed' ]] || missing=true
done
if "$missing"; then
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        usbmuxd libimobiledevice-utils ipheth-utils
fi

# eth1 is not a physical port identity: tethering can also receive that name.
if nmcli connection show KDX-Recovery-Service >/dev/null 2>&1; then
    nmcli connection modify KDX-Recovery-Service \
        match.path "${controller_path}-usb-0:1.2:*,${controller_path}-usb-0:2:*"
fi
profile=KDX-USB-WAN
if ! nmcli connection show "$profile" >/dev/null 2>&1; then
    nmcli connection add type ethernet con-name "$profile" ifname '*' \
        connection.autoconnect no
fi
nmcli connection modify "$profile" \
    connection.interface-name '' connection.autoconnect yes \
    connection.autoconnect-priority 100 \
    match.path "${controller_path}-usb-0:1.1:*,${controller_path}-usb-0:1:*" \
    match.driver 'rndis_host,cdc_ether,cdc_ncm,ipheth' \
    ipv4.method auto ipv4.route-metric 600 ipv4.dns-priority 600 \
    ipv4.ignore-auto-dns no ipv4.never-default no \
    ipv6.method disabled
printf 'USB phone WAN ready. Ethernet remains preferred (WAN metric 600). Backup: %s\n' "$backup"
