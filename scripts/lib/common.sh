#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_LIB_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=logging.sh
source "${SCRIPT_LIB_DIR}/logging.sh"

have_command() { command -v "$1" >/dev/null 2>&1; }

run_optional() {
    local title="$1"
    shift
    printf '\n===== %s =====\n' "${title}"
    if have_command "$1"; then
        "$@" 2>&1 || log_warn "Command failed or returned partial data: $*"
    else
        log_warn "Command unavailable: $1"
    fi
}

show_help_stub() {
    local name="$1"
    cat <<EOF
Usage: ${name} [--help]

This configuration action is intentionally disabled during Milestone 1.
EOF
}

disabled_action() {
    local name="$1"
    if [[ "${2:-}" == "--help" || "${2:-}" == "-h" ]]; then
        show_help_stub "${name}"
        return 0
    fi
    log_warn "${name} is not implemented in the read-only discovery phase."
    return 2
}
