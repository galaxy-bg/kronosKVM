#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run as root'; exit 1; }
[[ ! -e /opt/kdx-dashboard && ! -e /etc/kdx-dashboard && ! -e /etc/systemd/system/kdx-dashboard.service ]] || {
 echo 'Existing dashboard detected. Follow the upgrade instructions; no files changed.'; exit 1;
}
ss -lnt '( sport = :6000 )' | tail -n +2 | grep -q . && { echo 'Port 6000 is occupied'; exit 1; }
source_dir=$(cd "$(dirname "$0")/.." && pwd)
[[ -f "$source_dir/frontend/dist/index.html" ]] || { echo 'Build frontend before packaging'; exit 1; }
dnf install -y python3.11 python3.11-pip
id kdx-dashboard >/dev/null 2>&1 || useradd --system --home-dir /nonexistent --shell /sbin/nologin kdx-dashboard
install -d -m 0755 /opt/kdx-dashboard
install -d -m 0700 -o kdx-dashboard -g kdx-dashboard /etc/kdx-dashboard
tar -C "$source_dir" --exclude=.venv --exclude=node_modules --exclude=__pycache__ --exclude=.pytest_cache --exclude=.env -cf - . | tar -C /opt/kdx-dashboard -xf -
python3.11 /opt/kdx-dashboard/deploy/publish_static.py "$source_dir/frontend/dist" /opt/kdx-dashboard/frontend/dist
python3.11 -m venv /opt/kdx-dashboard/.venv
/opt/kdx-dashboard/.venv/bin/pip install -r /opt/kdx-dashboard/requirements.lock
cat > /etc/kdx-dashboard/server.env <<'CONFIG'
KDX_DASHBOARD_REGISTRATION_URL=http://172.12.2.77:3000
KDX_DASHBOARD_ALLOWED_ORIGINS=http://172.12.2.82:8081,http://172.12.2.78:6000
KDX_DASHBOARD_ALLOW_LAB_HTTP=true
KDX_DASHBOARD_SECURE_COOKIES=false
KDX_DASHBOARD_SESSION_SECONDS=28800
CONFIG
chmod 600 /etc/kdx-dashboard/server.env
chown kdx-dashboard:kdx-dashboard /etc/kdx-dashboard/server.env
install -m 0644 /opt/kdx-dashboard/deploy/kdx-dashboard.service /etc/systemd/system/
restorecon -RF /opt/kdx-dashboard /etc/kdx-dashboard
systemctl daemon-reload
systemctl enable --now kdx-dashboard
if systemctl is-active --quiet firewalld; then
 firewall-cmd --permanent --add-rich-rule='rule family="ipv4" source address="172.12.2.82/32" port port="6000" protocol="tcp" accept'
 firewall-cmd --add-rich-rule='rule family="ipv4" source address="172.12.2.82/32" port port="6000" protocol="tcp" accept'
fi
curl --fail --retry 15 --retry-connrefused --retry-delay 1 http://127.0.0.1:6000/health
printf '\nDashboard installed. Use existing Registration administrator/viewer token to sign in.\n'
