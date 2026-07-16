#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    printf 'Usage: health-check.sh\nChecks the localhost development API.\n'
    exit 0
fi
curl --fail --silent --show-error \
    --connect-timeout 2 \
    --max-time 5 \
    http://127.0.0.1:8000/api/v1/health
printf '\n'
