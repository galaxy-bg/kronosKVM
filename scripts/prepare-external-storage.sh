#!/usr/bin/env bash
set -Eeuo pipefail
install -d -m 0755 /mnt/kronoskvm-external
if ! mountpoint -q /mnt/kronoskvm-external; then
    mount --bind /mnt/kronoskvm-external /mnt/kronoskvm-external
fi
mount --make-rshared /mnt/kronoskvm-external
