#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_DIR=/opt/kronoskvm
DRY_RUN=false

usage() {
    cat <<'EOF'
Usage: install-containers.sh [--dry-run] [--help]

Install the KronosKVM application container definitions, build the ARM64 API
and web images, and enable kronoskvm-containers.service.

The native kronoskvm-api.service is stopped and disabled but retained as a
rollback path. Network/AP and hardware helper services remain on the host.
EOF
}

run() {
    if "${DRY_RUN}"; then
        printf '[DRY-RUN]'
        printf ' %q' "$@"
        printf '\n'
    else
        "$@"
    fi
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

command -v docker >/dev/null
command -v docker-compose >/dev/null

run install -m 0755 \
    "${PROJECT_DIR}/scripts/kronoskvm" \
    /usr/local/bin/kronoskvm

run install -d -m 0755 -o root -g root "${INSTALL_DIR}"
run install -d -m 0755 -o root -g root /etc/docker
run install -m 0644 \
    "${PROJECT_DIR}/deploy/docker/daemon.json" \
    /etc/docker/daemon.json

if "${DRY_RUN}"; then
    printf '[DRY-RUN] copy container application files to %q\n' "${INSTALL_DIR}"
else
    cp -a \
        "${PROJECT_DIR}/backend" \
        "${PROJECT_DIR}/config" \
        "${PROJECT_DIR}/frontend" \
        "${PROJECT_DIR}/deploy/nginx" \
        "${PROJECT_DIR}/Dockerfile" \
        "${PROJECT_DIR}/Dockerfile.web" \
        "${PROJECT_DIR}/compose.yaml" \
        "${PROJECT_DIR}/.dockerignore" \
        "${PROJECT_DIR}/pyproject.toml" \
        "${PROJECT_DIR}/README.md" \
        "${INSTALL_DIR}/"
fi

run install -m 0644 \
    "${PROJECT_DIR}/deploy/systemd/kronoskvm-containers.service" \
    /etc/systemd/system/kronoskvm-containers.service

if ! "${DRY_RUN}"; then
    systemctl enable docker.service
    systemctl restart docker.service
    systemctl daemon-reload
    systemctl disable --now kronoskvm-api.service || true
    (
        cd "${INSTALL_DIR}"
        docker-compose -f compose.yaml build
    )
    systemctl enable kronoskvm-containers.service
    systemctl restart kronoskvm-containers.service
fi

printf '[INFO] KronosKVM container installation complete.\n'
