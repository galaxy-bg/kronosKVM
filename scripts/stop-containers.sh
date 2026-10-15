#!/usr/bin/env bash
set -Eeuo pipefail

cd /opt/kronoskvm
docker-compose -f compose.yaml stop web
docker-compose -f compose.yaml stop guacd
docker rm --force kronoskvm-api >/dev/null 2>&1 || true
