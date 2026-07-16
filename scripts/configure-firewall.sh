#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat <<'EOF'
Usage: configure-firewall.sh

Firewall changes are deferred until the management interface is physically
mapped and a supported OS baseline is selected. Initial policy will preserve
SSH before applying a default-deny inbound ruleset.
EOF
    exit 0
fi

printf '[ERROR] Firewall configuration is blocked pending interface mapping.\n' >&2
exit 2
