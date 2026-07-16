#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat <<'EOF'
Usage: install-dependencies.sh

Package installation is intentionally deferred. Debian 11 Bullseye is not the
intended production baseline; select a supported Raspberry Pi OS image before
installing the application dependency set.
EOF
    exit 0
fi

printf '[ERROR] Dependency installation is blocked pending OS baseline decision.\n' >&2
exit 2
