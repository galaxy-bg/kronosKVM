# Dashboard English UI and operation tasks

Deployed 2026-11-01 to Dashboard VM `172.12.2.78`, available through the existing
[Management Console](https://185.251.66.26:18443/).

The interface uses English labels, the existing appliance logo, matching light/dark
colors and a collapsible sidebar. Theme preference is the only new browser-storage
value; credentials, configuration files and private keys are excluded.

Open **Tasks** in the sidebar or header to inspect management operations. Tasks have
queued/running/completed/failed/unconfirmed outcomes and a timestamped timeline.
The server request outcome is distinct from delayed cleanup on an offline device.
Unconfirmed operations require reviewing the actual record before retrying.
Read-only polling and authentication do not create tasks. The Registration Server
continues to own the separate audit log.

Deployment backup: `/var/backups/kdx-dashboard/english-tasks-20261101/before.tar.gz`
on the Dashboard VM. It contains private configuration; retain root-only access.
Task state: `/var/lib/kdx-dashboard/tasks.sqlite3` (directory 0700, database 0600,
service-owned), supplied by the systemd unit with a writable StateDirectory.

Validation:

- 34 dashboard Python tests passed, including task transitions, redaction, permissions,
  fail-closed storage errors, transport uncertainty and restart recovery.
- Two independent VPN configuration/crypto tests passed.
- Chrome smoke tests passed for English management flows, task details/filtering,
  light/dark switching, sidebar collapse and 390px mobile layouts.
- Production Vite build passed; WAN HTML and hashed assets use the new English build.
- Real WAN session created a rejected empty customer request (422) without modifying
  business data. Task `d610e62c-aa0f-48ea-bd68-afa1af202017` retained its
  queued → running → failed timeline after service restart.
- Existing one device, two customers and four VPN peer keys remained unchanged.
- Service healthy; no service error entries during validation.

The validation task remains visible as a failed form-validation request. It does
not indicate a production deployment failure. Existing browser sessions expire on
service restart; sign in again using the same access token.
