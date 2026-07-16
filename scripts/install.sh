#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "Bu betik root olarak çalıştırılmalıdır." >&2
    exit 1
fi

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
INSTALL_DIR=/opt/kronoskvm
CONFIG_DIR=/etc/kronoskvm

apt-get update
apt-get install -y python3 python3-venv

id kronoskvm >/dev/null 2>&1 || useradd --system --home "$INSTALL_DIR" --shell /usr/sbin/nologin kronoskvm

install -d -o kronoskvm -g kronoskvm "$INSTALL_DIR"
cp -R "$PROJECT_DIR"/. "$INSTALL_DIR"/
python3 -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/.venv/bin/pip" install "$INSTALL_DIR"

install -d -m 0750 -o root -g kronoskvm "$CONFIG_DIR"
if [ ! -f "$CONFIG_DIR/config.toml" ]; then
    install -m 0640 -o root -g kronoskvm \
        "$PROJECT_DIR/config/kronoskvm.example.toml" "$CONFIG_DIR/config.toml"
fi

install -m 0644 "$PROJECT_DIR/systemd/kronoskvm.service" \
    /etc/systemd/system/kronoskvm.service

chown -R kronoskvm:kronoskvm "$INSTALL_DIR"
systemctl daemon-reload
systemctl enable --now kronoskvm.service
