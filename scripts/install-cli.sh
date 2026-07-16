#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
DRY_RUN=false

usage() {
    printf 'Usage: install-cli.sh [--dry-run] [--help]\n'
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

if "${DRY_RUN}"; then
    printf '[DRY-RUN] install -m 0755 %q /usr/local/bin/kronoskvm\n' \
        "${PROJECT_DIR}/scripts/kronoskvm"
else
    install -m 0755 -o root -g root \
        "${PROJECT_DIR}/scripts/kronoskvm" \
        /usr/local/bin/kronoskvm
fi

printf '[INFO] KronosKVM CLI installation complete.\n'
