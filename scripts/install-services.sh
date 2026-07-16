#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
DRY_RUN=false

usage() {
    cat <<'EOF'
Usage: install-services.sh [--dry-run] [--help]

Install the KronosKVM Python application from the current checkout into
/opt/kronoskvm, create an isolated virtual environment and enable the
localhost-only API systemd service.
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

getent passwd kronoskvm >/dev/null
getent group kronoskvm >/dev/null
if ! id -nG kronoskvm | tr ' ' '\n' | grep -qx dialout; then
    run usermod --append --groups dialout kronoskvm
fi

run install -d -m 0755 -o root -g root /opt/kronoskvm

if "${DRY_RUN}"; then
    printf '[DRY-RUN] copy application files from %q to /opt/kronoskvm\n' "${PROJECT_DIR}"
else
    find /opt/kronoskvm -mindepth 1 -maxdepth 1 \
        ! -name .venv -exec rm -rf -- {} +
    cp -a \
        "${PROJECT_DIR}/backend" \
        "${PROJECT_DIR}/config" \
        "${PROJECT_DIR}/pyproject.toml" \
        "${PROJECT_DIR}/README.md" \
        /opt/kronoskvm/
fi

if [[ ! -x /opt/kronoskvm/.venv/bin/python ]]; then
    run python3 -m venv /opt/kronoskvm/.venv
fi
run /opt/kronoskvm/.venv/bin/python -m pip install --upgrade pip
run /opt/kronoskvm/.venv/bin/python -m pip install /opt/kronoskvm

if [[ ! -f /etc/kronoskvm/config.yaml ]]; then
    run install -m 0640 -o root -g kronoskvm \
        "${PROJECT_DIR}/config/kronoskvm.example.yaml" \
        /etc/kronoskvm/config.yaml
fi
if [[ ! -f /etc/kronoskvm/serial-profiles.yaml ]]; then
    run install -m 0640 -o root -g kronoskvm \
        "${PROJECT_DIR}/config/serial-profiles.example.yaml" \
        /etc/kronoskvm/serial-profiles.yaml
fi

run install -m 0644 \
    "${PROJECT_DIR}/deploy/systemd/kronoskvm-api.service" \
    /etc/systemd/system/kronoskvm-api.service

if ! "${DRY_RUN}"; then
    systemctl daemon-reload
    systemctl enable kronoskvm-api.service
    systemctl restart kronoskvm-api.service
fi

printf '[INFO] KronosKVM API installation complete.\n'
