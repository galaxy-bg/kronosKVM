#!/usr/bin/env bash
set -Eeuo pipefail

if (( EUID != 0 )); then
    printf '[ERROR] Run as root.\n' >&2
    exit 1
fi

systemctl disable --now kronoskvm-containers.service || true
systemctl enable kronoskvm-api.service
systemctl restart kronoskvm-api.service

printf '[INFO] Native KronosKVM API rollback complete.\n'
