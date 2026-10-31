# Rocky Linux 9 deployment, upgrade and recovery

Target only `172.12.2.77` (registration VM). Do not run these commands on the VPN,
Dashboard or Caddy hosts. The installer is for an empty VM; it refuses existing
application/configuration/database or an occupied API port. Review existing services
before changing them. Do not disable SELinux or firewalld.

## Initial installation

Validate locally first, including the PostgreSQL tests in TESTING.md. Copy the project
without `.venv`, `.env`, test state or private keys, unpack as root, then:

```sh
cd /root/kdx-registration-source
bash deploy/install-rocky.sh
systemctl status kdx-registration --no-pager
ss -lntp | grep -E ':3000|:5432'
getenforce
firewall-cmd --list-rich-rules
curl --fail http://127.0.0.1:3000/health
curl --fail http://172.12.2.82:8080/health
```

The installer installs Python 3.11 and PostgreSQL packages from Rocky repositories,
enables Chrony and requires synchronized server time, initializes a new loopback-only database, creates a dedicated role and service
account, installs locked Python requirements, generates a private server signing key,
runs `alembic upgrade head`, and creates a 90-day administrator token. It starts API
and daily ephemeral-state cleanup services. It only adds a firewall rule for Caddy
`172.12.2.82/32` to TCP 3000. PostgreSQL has no external listener or firewall opening.
Existing Caddy routing is used unchanged. HTTP lab mode is enabled explicitly.

The one-time bootstrap administrator token is in `/root/kdx-registration-admin.token`
(root-readable). It is not an SSH password. Retrieve through your approved secret
handling channel; do not paste into GitHub, screenshots or tickets.

Configuration: `/etc/kdx-registration/server.env` (service-owned 0600), signing key:
`/etc/kdx-registration/signing.pem` (0600), source/venv: `/opt/kdx-registration`
(root-owned). Service runs as `kdx-registration` with no shell, capabilities or write
access to the source. All database state lives in PostgreSQL.

## Local administration

As root, export the environment without displaying secrets:

```sh
cd /opt/kdx-registration
set -a
source /etc/kdx-registration/server.env
set +a
.venv/bin/python -m app.manage public-key
# Print a newly generated API token only to a secure terminal or redirect 0600 file.
umask 077
.venv/bin/python -m app.manage admin-create --name operator-2026 --role admin > /root/operator-2026.token
.venv/bin/python -m app.manage admin-create --name dashboard-viewer --role viewer > /root/dashboard-viewer.token
.venv/bin/python -m app.manage admin-disable --name operator-2026
.venv/bin/alembic current
```

Pin the printed server *public* key on clients out of band. Retain private signing
key backups; do not regenerate on upgrades. Administrator names are unique. Rotate
by creating a new name/token, updating clients, then disabling the old record.

## Upgrade

1. Run the test suite against a disposable database. Review migration SQL.
2. Take the database/config/source backups below; preserve the original source and
   venv in a dated release directory. Never run the initial installer again.
3. Stop the API and cleanup timer during migration. Replace application source from
   a verified archive, keeping `/etc/kdx-registration` untouched. Install locked
   requirements into a new venv and retain the previous venv for rollback.
4. With the environment loaded, run `.venv/bin/alembic upgrade head` as the service
   account; verify `.venv/bin/alembic current` and `.venv/bin/alembic check`.
5. Install any reviewed unit changes, `systemctl daemon-reload`, restart API and timer,
   check `/health` directly and through Caddy, unauthorized admin 401, and journal.

```sh
systemctl stop kdx-registration kdx-registration-cleanup.timer
# After copying reviewed sources and preparing the venv:
runuser -u kdx-registration --preserve-environment -- .venv/bin/alembic upgrade head
systemctl daemon-reload
systemctl start kdx-registration kdx-registration-cleanup.timer
journalctl -u kdx-registration -n 50 --no-pager
```

Do not blindly run Alembic downgrade in production. Review compatibility and restore
from backups deliberately if a migration is not backward compatible.

## Backup and recovery

As root, create a private backup. For an application-consistent source/config pair,
stop the API while taking the snapshot, or record the release/migration version.
`pg_dump` itself provides a consistent database snapshot.

```sh
umask 077
backup_dir=/var/backups/kdx-registration/$(date -u +%Y%m%dT%H%M%SZ)
install -d -m 0700 "$backup_dir"
runuser -u postgres -- pg_dump --format=custom kdx_registration > "$backup_dir/database.dump"
tar -czf "$backup_dir/private-config.tar.gz" /etc/kdx-registration
# Includes role credentials: protect this file like the private signing key.
runuser -u postgres -- pg_dumpall --globals-only > "$backup_dir/roles.sql"
tar --exclude=.venv --exclude=__pycache__ -czf "$backup_dir/source.tar.gz" /opt/kdx-registration
sha256sum "$backup_dir/"* > "$backup_dir/SHA256SUMS"
```

Encrypt backups before moving them off-host. Schedule daily backups and test a
restore into a separate isolated database/VM. Retain audit records under the required
retention policy. The cleanup timer removes only challenges/sessions expired for
more than one day; it retains tokens, registration events and audit history.

Recovery to a clean VM: install matching PostgreSQL/Python, recreate service account,
restore the source/venv and private configuration with original ownership/permissions,
restore necessary database roles, create an empty owned database, and `pg_restore`
the dump into it. Compare Alembic version with restored source before starting units.
Do not use `--clean` against a running or unreviewed database. Keep the server signing
key unchanged so issued documents and pinned clients remain consistent.

## HTTPS migration

Separately authorize Caddy production TLS/domain setup for `register.infrabox.io`.
Require HTTPS on all client-facing routes and update device URLs/pins. The service
currently ignores forwarded headers; either terminate TLS directly at Uvicorn using
an appropriately restricted TLS unit, or explicitly add a reviewed trusted-proxy
configuration accepting only the Caddy source address, then set
`KDX_ALLOW_LAB_HTTP=false`. Do not merely flip the flag behind an HTTP upstream and
assume X-Forwarded-Proto is trusted. No production DNS/TLS change is made here.
