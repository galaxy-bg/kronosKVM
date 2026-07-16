#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

DRY_RUN=false

usage() {
    cat <<'EOF'
Usage: bootstrap.sh [--dry-run] [--help]

Prepare the non-network KronosKVM base operating-system layout:

- create the locked kronoskvm service account and group
- create /etc, /var/lib, /var/log, /run and /opt directories
- preserve Europe/Istanbul timezone and active NTP configuration
- install tmpfiles and journald retention configuration

This script does not install packages, upgrade the OS, change networking,
configure a firewall, install services, edit boot files or reboot.
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

write_if_changed() {
    local target="$1"
    local mode="$2"
    local owner="$3"
    local group="$4"
    local temporary
    temporary="$(mktemp)"
    cat >"${temporary}"

    if [[ -f "${target}" ]] && cmp -s "${temporary}" "${target}"; then
        log_info "Unchanged: ${target}"
        rm -f -- "${temporary}"
        return
    fi

    if "${DRY_RUN}"; then
        log_info "Would install ${target}"
    else
        if [[ -e "${target}" ]]; then
            cp -a -- "${target}" "${target}.bak.$(date -u '+%Y%m%dT%H%M%SZ')"
        fi
        install -D -m "${mode}" -o "${owner}" -g "${group}" "${temporary}" "${target}"
        log_info "Installed: ${target}"
    fi
    rm -f -- "${temporary}"
}

while (( $# > 0 )); do
    case "$1" in
        --dry-run) DRY_RUN=true ;;
        --help|-h) usage; exit 0 ;;
        *) log_error "Unknown argument: $1"; usage >&2; exit 2 ;;
    esac
    shift
done

if (( EUID != 0 )); then
    log_error "Run as root (for example: sudo ./scripts/bootstrap.sh --dry-run)"
    exit 1
fi

log_info "Preparing KronosKVM base OS layout (dry_run=${DRY_RUN})"

if ! getent group kronoskvm >/dev/null; then
    run groupadd --system kronoskvm
else
    log_info "Group already exists: kronoskvm"
fi

if ! getent passwd kronoskvm >/dev/null; then
    run useradd \
        --system \
        --gid kronoskvm \
        --home-dir /var/lib/kronoskvm \
        --shell /usr/sbin/nologin \
        --comment "KronosKVM service account" \
        kronoskvm
else
    log_info "User already exists: kronoskvm"
fi

run install -d -m 0750 -o root -g kronoskvm /etc/kronoskvm
run install -d -m 0750 -o kronoskvm -g kronoskvm /var/lib/kronoskvm
run install -d -m 0750 -o kronoskvm -g kronoskvm /var/lib/kronoskvm/images
run install -d -m 0750 -o kronoskvm -g kronoskvm /var/log/kronoskvm
run install -d -m 0755 -o root -g root /opt/kronoskvm

write_if_changed /etc/tmpfiles.d/kronoskvm.conf 0644 root root <<'EOF'
d /run/kronoskvm 0750 kronoskvm kronoskvm -
EOF

write_if_changed /etc/systemd/journald.conf.d/kronoskvm.conf 0644 root root <<'EOF'
[Journal]
Storage=persistent
SystemMaxUse=256M
RuntimeMaxUse=64M
MaxRetentionSec=14day
Compress=yes
EOF

if ! "${DRY_RUN}"; then
    systemd-tmpfiles --create /etc/tmpfiles.d/kronoskvm.conf
    systemctl restart systemd-journald
fi

if [[ "$(timedatectl show -p Timezone --value)" != "Europe/Istanbul" ]]; then
    log_warn "Timezone differs from Europe/Istanbul; not changing automatically."
fi

if [[ "$(timedatectl show -p NTPSynchronized --value)" != "yes" ]]; then
    log_warn "NTP is not synchronized; review before production use."
fi

log_info "Base OS preparation complete."
