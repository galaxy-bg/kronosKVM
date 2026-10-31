# Dashboard deployment — 2026-10-31

Owner requested the Dashboard on the previously identified VM and its relationship
with the Registration Server. Installed on Rocky Linux VM `172.12.2.78`, listening
on TCP 6000. The existing Caddy entry point is **http://172.12.2.82:8081**.
Caddy configuration, WireGuard and physical-device registration configuration were
not modified by this deployment.

## Installed state

- `/opt/kdx-dashboard`: source, compiled React assets and Python 3.11 virtualenv.
- `/etc/kdx-dashboard/server.env`: service-owned mode 0600 configuration.
- `kdx-dashboard.service`: enabled and running as dedicated non-login user
  `kdx-dashboard`, with read-only filesystem and NoNewPrivileges.
- Dashboard holds no database credentials, default API key or user SSH password.
- Sign in with a Registration administrator/viewer API access key. The existing
  initial key remains on Registration VM `.77` at
  `/root/kdx-registration-admin.token`, root-readable only.
- Dashboard VM firewalld was already inactive and SELinux already Permissive at
  inspection; the installer did not change those states.

Registration received authenticated read endpoints for current actor, customers,
licenses and audit events. Existing device summaries gained nested customer/license
objects and new/unactivated installation IDs. There are **no schema migrations**.
The original live device/license bindings remained unchanged.

## Verification

- Registration staged code: **24 tests passed on the target PostgreSQL/Python 3.11**,
  including new Dashboard read endpoints and reinstallation-review behavior. The
  separate disposable test database was removed afterward.
- Dashboard gateway: **10 integration/security tests passed locally** against the
  actual Registration application (session handling, CSRF/origin, roles, revocation,
  logout, fixed routes, rate limiting and explicit approval).
- React production build passed. Desktop and 390px mobile Chrome fixture tests passed:
  navigation, pending filtering, device/customer/license relation drawer, search and
  intentional approval/token dialog. These browser tests used synthetic records,
  not real production mutations. Screenshots are in `artifacts/dashboard`.
- Live Caddy HTTP: page and health 200. Real API key sign-in, inventory retrieval,
  device detail, missing-CSRF rejection, logout and post-logout denial all passed.
- Live inventory contained two devices/customers/licenses: one earlier revoked
  simulated test identity and the real active InfraBox. No test pending device was
  inserted into the live database for UI screenshots.
- Real relationship verified through the gateway:
  `KronosDX Lab → DEMO (expires 2026-11-30 22:19 Europe/Istanbul)
  → 10000000000865DD (ACTIVE)`.
- No failed systemd units on either VM after installation.

## Backups and operational notes

Registration pre-upgrade source/database:
`/var/backups/kdx-registration/pre-dashboard-20261031`.
Dashboard initial private source/config snapshot:
`/var/backups/kdx-dashboard/initial-20261031`.
Installation log: `/root/kdx-dashboard-install-20261031.log` on `.78`.
Live integration summary: `/root/kdx-dashboard-live-validation.json` on `.77`.

The Dashboard is internal lab HTTP and has not been published to WAN. Before public
access, configure HTTPS, Secure cookies, exact HTTPS allowed origins, appropriate
network restrictions and production security review. Registration devices' temporary
workstation SSH relay remains a separate network limitation described in
`device-registration/DEPLOYMENT-20261031.md`.

Approval remains deliberate: inspect serial, installation and public key, choose an
active license and give a reason. The resulting single-use token must be delivered
to the device; the Dashboard does not silently activate a device or collect its SSH
credentials. Restore/reassignment and revocation also require explicit operator
confirmation and a recorded reason. Viewer users have no mutation controls or API
permission to mutate.

## Subsequent verified WAN integration

The real device subsequently moved to `https://185.251.66.26:18444` using an
explicitly provisioned lab CA and normal certificate/IP verification. Its temporary
workstation relay was removed, and real reboot/automatic reauthentication passed
with unchanged customer/license binding. Public Dashboard TLS sign-in at
`https://185.251.66.26:18443` was verified; the existing gateway received the exact
HTTPS origin and Secure-cookie handling. Caddy/FortiGate/VPN configuration and
Registration schema were preserved. See
`device-registration/docs/WAN-ACCEPTANCE-20261031.md` for current evidence.
