#!/usr/bin/env bash
set -Eeuo pipefail
[[ ${EUID} -eq 0 ]] || { echo 'Run as root' >&2; exit 1; }
cd /opt/kronoskvm
install -d -m 0750 -o 10001 -g 20 /var/lib/kronoskvm/state
if [[ ! -e /var/lib/kronoskvm/state/wifi.lock ]]; then
    install -m 0600 -o 10001 -g 20 /dev/null /var/lib/kronoskvm/state/wifi.lock
fi
install -m 0644 deploy/systemd/kronoskvm-wifi* /etc/systemd/system/
install -d -m 0755 /etc/systemd/system/kronoskvm-containers.service.d
install -m 0644 deploy/systemd/kronoskvm-containers-wifi.conf /etc/systemd/system/kronoskvm-containers.service.d/wifi.conf
systemctl daemon-reload
# Applying again preserves a previously selected custom password.
python3 scripts/wifi-host.py --apply
systemctl enable --now kronoskvm-wifi.service
systemctl enable --now kronoskvm-wifi-action.path kronoskvm-wifi-status.timer
