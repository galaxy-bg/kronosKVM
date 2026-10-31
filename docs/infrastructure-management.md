# InfraBox infrastructure management — 2026-11-01

| Component | Source | Internal service | Responsibility |
| --- | --- | --- | --- |
| Appliance | `backend/`, `frontend/` | `192.168.31.27` | KVM, local Settings, registration snapshot |
| Device agent | `device-registration/` | host systemd timer | Identity, enrollment, proofs, offline grace |
| Registration | `registration-server/` | `172.12.2.77:3000` | PostgreSQL authority, customers, licenses, audit |
| Dashboard | `dashboard/` | `172.12.2.78:6000` | Browser administration and same-origin API gateway |
| VPN telemetry | `dashboard/vpn-monitor/` | `172.12.2.74` | Public peer statistics via restricted SSH |
| Existing Caddy | external VM configuration | `172.12.2.82` | HTTPS entry points and reverse proxy |

## Current verified behavior

The real appliance enrolls PENDING. A separate administrator approves the exact
serial/installation/public-key binding and assigns a license; a one-use token
lets the device activate. The deployed lab device has a 30-day DEMO license.
Normal boots authenticate with fresh challenges. Signed offline grace is bounded
and identity-specific; a copied SD card on different hardware is rejected.

Dashboard administrators can create and edit customers (company, contact, email,
phone), pre-register devices and edit their display name, notes and customer
association. Email remains unverified. Device creation does not activate it.
Licensed ownership changes use the explicit recovery/reassignment workflow.

Deletion is reversible archival with audit/history preservation. Active device
authorization must be stopped first; customers with active licenses or relevant
active device associations are protected. Restore does not reactivate a device.
Viewers cannot mutate records. Browser sessions use HttpOnly cookies and CSRF
checks; the gateway has no database password.

VPN monitoring reports interface state, public keys, allowed IPs, handshake age
and traffic. Registered-peer serials link to customer/device records. Stale or
unavailable telemetry is displayed as unknown. Monitoring does not change VPN
routing, keys, tunnels or firewall rules.

WAN dashboard: `https://185.251.66.26:18443`; registration:
`https://185.251.66.26:18444`. These lab endpoints use the explicitly provisioned
lab CA. Keep certificate and hostname/IP verification enabled. See the
[WAN acceptance report](../device-registration/docs/WAN-ACCEPTANCE-20261031.md).

## Installation and upgrades

Use each component's README and deployment directory. Initial installers refuse
existing installations; do not run them as upgrade scripts. Back up PostgreSQL,
application source and private identity/configuration separately. For the latest
management update, migrate registration to Alembic `0002` before updating the
dashboard. Publish built assets with `dashboard/deploy/publish_static.py` so the
service user can read the page and hashed assets. Keep secrets outside Git.

Source publication does not install updates automatically. Existing Caddy,
FortiGate and WireGuard configuration remains managed on the respective servers.
The proposed 60-day evaluation/login wizard is not implemented in this release.

## Validation

Run appliance tests from the repository root with `.venv/bin/python -m pytest -q`.
Registration tests run from `registration-server/` with its own environment.
From root, `PYTHONPATH=registration-server registration-server/.venv/bin/python
-m pytest registration-server/tests dashboard/tests device-registration/tests -q`
checks the central services and agent. PostgreSQL concurrency tests require a
separate disposable test database and are skipped without one. Socket/TLS tests
need local network permissions. Build the dashboard with
`npm ci --prefix dashboard/frontend` and `npm run build --prefix dashboard/frontend`.
Browser smoke tests use synthetic fixtures; see `dashboard/tests/ui-smoke.mjs`.
