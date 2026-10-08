#!/usr/bin/env bash
set -Eeuo pipefail
[[ ${EUID} -eq 0 ]] || { echo 'Run as root' >&2; exit 1; }
cd /opt/kronoskvm
command -v nft >/dev/null
test -d /sys/class/net/br-recovery
test -d /sys/class/net/wlan0
backup=$(mktemp -d /var/backups/kronoskvm/ap-access-install.XXXXXX)
cp -a /etc/dnsmasq.d "$backup/"
# The dynamic file becomes the sole owner of router/DNS DHCP options.
for file in /etc/dnsmasq.d/kronoskvm-ap.conf /etc/dnsmasq.d/kronoskvm-recovery.conf; do
    [[ ! -f "$file" ]] || sed -i '/^dhcp-option=option:router$/d; /^dhcp-option=option:dns-server$/d' "$file"
done
if [[ ! -e /var/lib/kronoskvm/state/ap-access.lock ]]; then
    install -m 0600 -o 10001 -g 20 /dev/null /var/lib/kronoskvm/state/ap-access.lock
fi
install -m 0644 deploy/systemd/kronoskvm-ap-access* /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now kronoskvm-ap-access.service
systemctl enable --now kronoskvm-ap-access-action.path kronoskvm-ap-access-status.timer
printf 'DNS_BACKUP=%s\n' "$backup"
