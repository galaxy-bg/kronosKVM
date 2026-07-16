#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
# shellcheck source=lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

usage() {
    cat <<'EOF'
Usage: remote-inventory.sh [ssh-host]

Run inventory.sh remotely through SSH without installing it. The default host
is "kronoskvm". Output is saved under artifacts/inventory/ and is ignored by Git.
EOF
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    usage
    exit 0
fi
if (( $# > 1 )); then
    usage >&2
    exit 2
fi

host="${1:-kronoskvm}"
timestamp="$(date -u '+%Y%m%dT%H%M%SZ')"
output_dir="${PROJECT_DIR}/artifacts/inventory"
output_file="${output_dir}/${host//[^a-zA-Z0-9._-]/_}-${timestamp}.txt"
mkdir -p -- "${output_dir}"

log_info "Running read-only inventory on ${host}"
ssh "${host}" 'bash -s' <"${SCRIPT_DIR}/inventory.sh" | tee "${output_file}"
chmod 600 "${output_file}"
log_info "Saved local private artifact: ${output_file}"
