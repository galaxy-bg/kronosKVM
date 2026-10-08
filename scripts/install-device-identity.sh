#!/usr/bin/env bash
set -Eeuo pipefail
[[ ${EUID} -eq 0 ]] || { echo 'Run as root' >&2; exit 1; }
cd /opt/kronoskvm
# Validate/migrate using the current hardware before enabling boot provisioning.
python3 scripts/device-identity.py --apply
install -m 0644 deploy/systemd/kronoskvm-device-identity.service /etc/systemd/system/
install -d -m 0755 /etc/systemd/system/kronoskvm-containers.service.d
install -m 0644 deploy/systemd/kronoskvm-containers-identity.conf \
    /etc/systemd/system/kronoskvm-containers.service.d/identity.conf
systemctl daemon-reload
systemctl enable --now kronoskvm-device-identity.service
# Recreate the API with the host's new name; does not reboot the OS.
systemctl reload kronoskvm-containers.service
