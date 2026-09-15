#!/usr/bin/env bash
set -Eeuo pipefail
# Run from the installed /opt/kronoskvm checkout. Services start on demand in UI.
[[ ${EUID} -eq 0 ]] || { echo 'Run as root' >&2; exit 1; }
command -v dnsmasq >/dev/null
command -v python3 >/dev/null
if ! getent passwd 10001 >/dev/null; then
    useradd --uid 10001 --gid 20 --no-create-home --home-dir /nonexistent \
        --shell /usr/sbin/nologin kronoskvm-recovery
fi
install -d -m 0750 -o 10001 -g 20 /mnt/kronoskvm-storage/recovery
install -m 0644 /opt/kronoskvm/deploy/systemd/kronoskvm-recovery-{http,tftp}.service /etc/systemd/system/
install -m 0644 /opt/kronoskvm/deploy/systemd/kronoskvm-service-status.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now kronoskvm-service-status.timer
systemctl enable --now kronoskvm-service-action.path
