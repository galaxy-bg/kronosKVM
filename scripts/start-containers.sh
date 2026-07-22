#!/usr/bin/env bash
set -Eeuo pipefail

cd /opt/kronoskvm
version="${KRONOSKVM_VERSION:-dev}"

docker rm --force kronoskvm-api >/dev/null 2>&1 || true
docker run --detach \
    --name kronoskvm-api \
    --network host \
    --hostname kronoskvm \
    --restart unless-stopped \
    --read-only \
    --user 10001:20 \
    --cap-drop ALL \
    --security-opt no-new-privileges:true \
    --device-cgroup-rule 'c 188:* rmw' \
    --volume /dev:/dev:rw \
    --tmpfs /tmp:size=16m,mode=1777 \
    --volume /sys:/sys:ro \
    --volume /sys/firmware/devicetree/base:/run/kronoskvm/device-tree:ro \
    --volume /etc/kronoskvm:/etc/kronoskvm:ro \
    --volume /mnt/kronoskvm-storage:/storage \
    --env KRONOSKVM_STORAGE_PATH=/storage \
    --env KRONOSKVM_STORAGE_REQUIRE_MARKER=1 \
    "kronoskvm-api:${version}" >/dev/null

docker-compose -f compose.yaml up --detach --no-deps web
