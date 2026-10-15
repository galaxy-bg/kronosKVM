#!/usr/bin/env bash
set -Eeuo pipefail
[[ ${EUID} -eq 0 ]] || { echo 'Run as root' >&2; exit 1; }
cd /opt/kronoskvm
# One interface owner: retain existing NetworkManager/systemd host services.
if systemctl is-active --quiet wg-quick@wg-kdx.service; then
    echo 'wg-quick already owns wg-kdx. Resolve ownership before installing.' >&2
    exit 1
fi
bash scripts/install-remote-assist.sh
install -d -m 0700 /etc/wireguard
chmod 0755 scripts/infrabox-wireguard.py
printf 'Provisioning host installed. No identity, peer or VPN connection was changed.\n'
