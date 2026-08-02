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
    --group-add 44 \
    --cap-drop ALL \
    --security-opt no-new-privileges:true \
    --device-cgroup-rule 'c 188:* rmw' \
    --device-cgroup-rule 'c 81:* rmw' \
    --device-cgroup-rule 'c 236:* rmw' \
    --volume /dev:/dev:rw \
    --tmpfs /tmp:size=16m,mode=1777 \
    --volume /sys:/sys:ro \
    --volume /sys/firmware/devicetree/base:/run/kronoskvm/device-tree:ro \
    --volume /etc/kronoskvm:/etc/kronoskvm:ro \
    --volume /mnt/kronoskvm-storage:/storage \
    --volume /var/lib/kronoskvm/state:/state \
    --volume /var/log/kronoskvm:/logs \
    --env KRONOSKVM_STORAGE_PATH=/storage \
    --env KRONOSKVM_STORAGE_REQUIRE_MARKER=0 \
    --env KRONOSKVM_STORAGE_CAPACITY_BYTES=34359738368 \
    --env KRONOSKVM_STORAGE_RESERVE_BYTES=10737418240 \
    --env KRONOSKVM_STORAGE_POOL_ID=internal \
    --env 'KRONOSKVM_STORAGE_LABEL=Internal SD · 32G' \
    --env KRONOSKVM_STORAGE_TYPE=internal \
    --env KRONOSKVM_STATE_PATH=/state \
    --env KRONOSKVM_LOG_PATH=/logs/application.jsonl \
    --env KRONOSKVM_LOG_MAX_BYTES=10485760 \
    --env KRONOSKVM_LOG_BACKUP_COUNT=5 \
    "kronoskvm-api:${version}" >/dev/null

docker-compose -f compose.yaml up --detach --no-deps web
