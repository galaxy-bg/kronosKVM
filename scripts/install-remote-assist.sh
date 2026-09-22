#!/usr/bin/env bash
set -Eeuo pipefail
[[ ${EUID} -eq 0 ]] || { echo 'Run as root' >&2; exit 1; }
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
cd /opt/kronoskvm
if ! command -v wg >/dev/null; then
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends wireguard-tools
fi
modprobe wireguard
install -d -m 0700 /etc/kronoskvm/remote-assist
if [[ ! -e /var/lib/kronoskvm/state/remote-assist.lock ]]; then
    install -m 0600 -o 10001 -g 20 /dev/null /var/lib/kronoskvm/state/remote-assist.lock
fi
install -m 0644 deploy/systemd/kronoskvm-remote-assist-* /etc/systemd/system/
systemctl daemon-reload
systemctl enable kronoskvm-remote-assist-boot.service
systemctl enable --now kronoskvm-remote-assist-action.path kronoskvm-remote-assist-status.timer
python3 scripts/remote-assist-host.py
