#!/usr/bin/env bash
# New service only. Existing services/configuration cause an explicit stop.
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run as root'; exit 1; }
[[ ! -e /opt/kdx-registration && ! -e /etc/kdx-registration && ! -e /var/lib/pgsql/data/PG_VERSION ]] || {
 echo 'Existing installation/database detected. Follow the upgrade guide; no files changed.'; exit 1;
}
ss -lnt '( sport = :3000 )' | tail -n +2 | grep -q . && { echo 'Port 3000 is occupied'; exit 1; }
source_dir=$(cd "$(dirname "$0")/.." && pwd)
dnf install -y python3.11 python3.11-pip postgresql-server postgresql-contrib chrony
systemctl enable --now chronyd
# Time-limited licensing requires synchronized server time before issuance.
chronyc waitsync 30 0.5 0 1
postgresql-setup --initdb
# Loopback TCP only. Keep local peer authentication; password auth for app role.
sed -i "s/^#listen_addresses =.*/listen_addresses = '127.0.0.1'/" /var/lib/pgsql/data/postgresql.conf
sed -i -E '/^host[[:space:]]+all[[:space:]]+all[[:space:]]+127\.0\.0\.1\/32/s/(ident|md5|trust)$/scram-sha-256/' /var/lib/pgsql/data/pg_hba.conf
systemctl enable --now postgresql
id kdx-registration >/dev/null 2>&1 || useradd --system --home-dir /var/lib/kdx-registration --shell /sbin/nologin kdx-registration
install -d -m 0755 /opt/kdx-registration
# Source tree excludes local test and secret state.
tar -C "$source_dir" --exclude=.venv --exclude=.env --exclude=__pycache__ --exclude=.pytest_cache --exclude='*.db' -cf - . | tar -C /opt/kdx-registration -xf -
install -d -m 0700 -o kdx-registration -g kdx-registration /etc/kdx-registration /var/lib/kdx-registration
python3.11 -m venv /opt/kdx-registration/.venv
/opt/kdx-registration/.venv/bin/pip install -r /opt/kdx-registration/requirements.lock
cd /opt/kdx-registration
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider
# Generate all secrets locally. No passwords in argv, logs or source archives.
python3.11 - <<'PY'
import pathlib,secrets,subprocess
password=secrets.token_hex(32)
sql="SET password_encryption='scram-sha-256'; CREATE ROLE kdx_registration LOGIN PASSWORD '"+password+"'; CREATE DATABASE kdx_registration OWNER kdx_registration;"
subprocess.run(['runuser','-u','postgres','--','psql','-v','ON_ERROR_STOP=1'],input=sql,text=True,check=True)
p=pathlib.Path('/etc/kdx-registration/server.env')
p.write_text('KDX_DATABASE_URL=postgresql+psycopg://kdx_registration:'+password+'@127.0.0.1/kdx_registration\nKDX_SIGNING_KEY=/etc/kdx-registration/signing.pem\nKDX_ALLOW_LAB_HTTP=true\nKDX_OFFLINE_GRACE_SECONDS=86400\n')
p.chmod(0o600)
PY
chown kdx-registration:kdx-registration /etc/kdx-registration/server.env
cd /opt/kdx-registration
set -a; source /etc/kdx-registration/server.env; set +a
runuser -u kdx-registration --preserve-environment -- .venv/bin/python -m app.manage keygen
runuser -u kdx-registration --preserve-environment -- .venv/bin/alembic upgrade head
# One initial administrator; token exists only in a root-readable local file.
.venv/bin/python -m app.manage admin-create --name lab-admin > /root/kdx-registration-admin.token
chmod 600 /root/kdx-registration-admin.token
install -m 0644 deploy/kdx-registration*.service deploy/kdx-registration*.timer /etc/systemd/system/
restorecon -RF /opt/kdx-registration /etc/kdx-registration /var/lib/kdx-registration
systemctl daemon-reload
systemctl enable --now kdx-registration.service kdx-registration-cleanup.timer
# Only the existing Caddy VM may reach the new HTTP listener.
firewall-cmd --permanent --add-rich-rule='rule family="ipv4" source address="172.12.2.82/32" port port="3000" protocol="tcp" accept'
firewall-cmd --add-rich-rule='rule family="ipv4" source address="172.12.2.82/32" port port="3000" protocol="tcp" accept'
curl --fail --retry 15 --retry-connrefused --retry-delay 1 http://127.0.0.1:3000/health
printf '\nInstalled. Administrator token: /root/kdx-registration-admin.token (do not publish).\n'
