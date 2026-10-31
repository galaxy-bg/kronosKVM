# InfraBox Management Dashboard

React administration UI with a FastAPI gateway, deployed on the Dashboard VM
`172.12.2.78:6000`. User entry point: `http://172.12.2.82:8081` through the existing
Caddy route. Registration VM remains the source of truth for all device, customer,
license and audit records. The dashboard has no PostgreSQL credentials or direct
access to device private keys.

## Features

- Overview with device/activation/review counts and customer → license → device flow.
- Device inventory, serial/customer search, status filter and identity detail drawer.
- Pending devices plus new unactivated installations on an already active device.
- Customer list with license/device associations; explicit customer creation.
- License list with capacity, expiry, connected devices; creation, renewal and suspension.
- Explicit device approval, suspension, revocation and controlled recovery dialogs.
- One-time activation token returned only after an intentional approval action.
- Central audit/registration history, including observed hardware mismatch details.
- Read-only viewer role and administrator role; roles enforced upstream and by gateway.
- Responsive Turkish interface, dates displayed in Europe/Istanbul time.

## Sign-in

Use an existing Registration administrator or viewer API access key. The initial
administrator key is kept on Registration VM `.77` at
`/root/kdx-registration-admin.token` (root-only). It is not the SSH password. Enter
it into the dashboard password field; do not publish it or place it in URLs.

The browser submits the key once to this same-origin server. The gateway validates
it against `/api/v1/admin/session` and holds it only in an expiring in-memory session.
The browser receives a random HttpOnly/SameSite=Strict cookie and separate CSRF value.
No API key goes into localStorage, sessionStorage, HTML or persistent dashboard files.
Logout/service restart discards the server session. Session duration is capped at
8 hours and at the upstream credential's own expiry. Each upstream operation still
validates the credential, so revoked users lose access.

Lab HTTP is explicit. Before Internet exposure, deploy HTTPS, set
`KDX_DASHBOARD_SECURE_COOKIES=true`, remove lab HTTP configuration as appropriate,
and configure exact allowed HTTPS origins. The dashboard is currently intended for
the internal lab; the WAN dashboard is now available at `https://185.251.66.26:18443` with the provisioned lab CA. See [current infrastructure status](../docs/infrastructure-management.md).

## Source and local development

- `frontend/`: React/Vite, Lucide icons, compiled assets.
- `backend/main.py`: same-origin authentication, session/CSRF checks, fixed API gateway.
- `tests/test_gateway.py`: integration/security tests against the actual Registration app.
- `tests/ui-smoke.mjs`: Chrome desktop/mobile tests using synthetic API fixtures only.
- `deploy/`: Rocky installation script and restricted non-root systemd unit.

```sh
npm ci --prefix frontend
npm run build --prefix frontend
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.lock
# Set allow_lab_http and allowed_origins explicitly for a local preview.
KDX_DASHBOARD_ALLOW_LAB_HTTP=true \
KDX_DASHBOARD_ALLOWED_ORIGINS=http://127.0.0.1:16079 \
.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 16079 --no-proxy-headers
```

From repository root, using the Registration development environment:

```sh
PYTHONPATH=registration-server registration-server/.venv/bin/python -m pytest -q \
  registration-server/tests dashboard/tests
# Browser fixtures: serve frontend/dist at 127.0.0.1:16078 first.
node dashboard/tests/ui-smoke.mjs
```

PostgreSQL test databases must be disposable and contain `test` in their name;
server test fixtures drop and recreate their schema. Never use the real registration
database as a test database.

## Registration API additions

Dashboard integration adds authenticated GET endpoints `/api/v1/admin/session`,
`/customers`, `/licenses`, `/events`. Device summaries retain existing fields and
add nested customer/license relationships and unactivated installation IDs.
There are no database schema changes. A pending/new installation does not change
the original device binding, and approval does not itself activate the device.
No existing real-device status/license is changed by deployment.

## Rocky deployment

Build frontend locally, package source + frontend/dist (exclude node_modules, .venv,
.env and runtime data), then run `bash deploy/install-rocky.sh` as root on `.78`.
The installer refuses an existing installation or occupied port, creates non-login
service user `kdx-dashboard`, installs Python 3.11 requirements and starts the
systemd unit. It leaves the current SELinux/firewalld state unchanged; if firewalld
is already active, it adds only a `.82/32` rule for TCP 6000. It does not change Caddy.

Source: `/opt/kdx-dashboard`; configuration: `/etc/kdx-dashboard/server.env` (0600).
Service: `kdx-dashboard.service`, non-root, read-only filesystem and no capabilities.
Exactly one worker is required for the current in-memory session/rate-limit store.
Restarting logs out dashboard users but has no effect on device registration state.

Back up reviewed source/configuration before upgrades and keep the previous venv.
Registration changes should be backed up with `pg_dump` plus the previous application
source, even though this release has no migration. Roll back the dashboard by
stopping its service and restoring its previous source/venv; roll back Registration
by restoring the previous API source and restarting its unit. Never restore a stale
database merely to roll back these read-API additions.

## Scope and limits

Each dashboard snapshot fetches the first 200 devices/customers/licenses and last
200 audit events. A visible notice appears if an inventory limit is reached. This is
sufficient for the present lab; add server-side pagination before fleet-scale use.
Refresh runs every minute or on demand. Last device validation is a successful
license check timestamp, not proof of a currently connected interactive session.
Review counts include hardware mismatch evidence present in the fetched audit window.

Approval tokens appear only in the explicit result dialog, are not retained on the
dashboard, and must be transferred to the device securely. The initial UI does not
push activation tokens or store SSH credentials. WireGuard peer inventory is not
fabricated or queried from the separate VPN server in this phase.

## VPN monitoring

The VPN tab now shows public WireGuard status, handshake recency, server-side
traffic and managed-peer→customer/device association. It is read-only and uses a
forced-command SSH reader, not the VPN root password. See
[vpn-monitor/README.md](vpn-monitor/README.md) for installed paths, security,
field semantics, validation and recovery. Current licensed device `.11` is linked
through the managed peer registry's serial; VPN availability never grants a license.

## Static frontend upgrades

Use the publisher instead of copying directory metadata from a private root staging
directory. It installs directories 0755 and files 0644 even under umask 077, publishes
index.html last, and keeps previous hashed assets available:

```sh
python3.11 /opt/kdx-dashboard/deploy/publish_static.py \
  /root/reviewed-release/frontend/dist /opt/kdx-dashboard/frontend/dist
runuser -u kdx-dashboard -- test -r /opt/kdx-dashboard/frontend/dist/index.html
curl --fail http://127.0.0.1:6000/
```

Validate the page **and its referenced JS/CSS** through Caddy after deployment; the
health endpoint alone does not verify that the service user can read public assets.

### Customer and device management (2026-11-01)

Administrators can create/edit customer names, contacts, email and phone, and pre-register devices with a hardware serial, model, display name, customer and notes. Contact email is stored as unverified; no email is sent. Device identity fields cannot be edited and manual creation never activates a device.

“Sil / arşivle” retains the record, license bindings and audit history. Active devices must first be suspended/revoked; customers with active licenses or active/suspended devices cannot be archived. Archived records are hidden by default; use “Arşivlenenleri göster” to restore them. Restoring an archived device leaves it revoked and requires the existing explicit recovery/approval flow. Licensed device ownership changes require controlled reassignment.

Deployment requires registration migration `0002` before the new dashboard. Back up the registration database and both application trees; deploy registration app/model/schema and migration, run `alembic upgrade head` with the existing protected environment, restart registration, then publish the dashboard assets with `deploy/publish_static.py` and restart the gateway. Preserve all server secrets and VPN configuration. Verify the actual page/assets and authenticated overview, rather than `/health` alone.

Live deployment backups: `/var/backups/kdx-registration/management-20261101` (including PostgreSQL dump), `/var/backups/kdx-dashboard/management-20261101`. TLS WAN verification confirmed the page, both assets, management fields and three VPN peers. No production records were created, edited or archived for verification.
