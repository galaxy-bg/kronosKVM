# Validation and deployment record — 2026-10-31

Installed on Registration VM `172.12.2.77` following explicit authorization to upload
and install. No Caddy, WireGuard or Dashboard configuration changes were made. A separate
physical-device agent was subsequently installed with explicit owner approval; see
`device-registration/DEPLOYMENT-20261031.md` in the repository.

## Installed service

- Rocky Linux 9.5, Python 3.11.13, PostgreSQL 13.23.
- Source/venv: `/opt/kdx-registration`.
- API: TCP 3000, non-root `kdx-registration` systemd service.
- PostgreSQL: `127.0.0.1:5432` only; no public database exposure.
- Firewall: only Caddy `172.12.2.82/32` allowed to reach API port 3000.
- Private server configuration/key: `/etc/kdx-registration`, directory 0700,
  files 0600, owned by the service account.
- Initial administrator bearer token: `/root/kdx-registration-admin.token`, root 0600.
  This is an API credential, separate from SSH; never commit or paste it into tickets.
- Server public signing key (provision/pin out of band):
  `IIBc5WnNs3xO7fipe49mcImcm1OrsyWH08K2PErjiy0=`.
- Daily expired-challenge/session cleanup timer enabled and tested.
- No failed systemd units after deployment.

The uploaded application archive SHA-256 was
`dac9001d385dfe44ebeb3e0d5b34a2195508a9f19b747a52e1476503542abc36`.
Original upload: `/root/kdx-registration-20261031.tar.gz`; install log:
`/root/kdx-registration-install-20261031.log`.

## Validation

- Local Python 3.14 / PostgreSQL 16: 21 tests passed, including concurrent duplicate
  enrollment/activation, license-capacity races and commit-failure rollback.
- Target Python 3.11 / SQLite: 19 passed, two PostgreSQL concurrency tests skipped.
- Target Python 3.11 / PostgreSQL 13: all 21 tests passed in a separate disposable
  test database; that database was removed after validation.
- Alembic revision `0001 (head)`; `alembic check` reports no missing operations.
- Live HTTP: health/docs/OpenAPI 200; unauthenticated admin requests 401.
- Live virtual-device workflow: pending enrollment, admin approval, activation,
  signed grace-document verification, clone mismatch detection, original-binding
  preservation, and device/license revocation all passed.
- The simulated device and DEMO license were revoked after validation; their
  customer, device and audit records are intentionally retained as test history.
  Device ID: `5c3ee156-dc89-4562-b3ed-d9673cf00f8a`.
- Ruff lint/format and installer shell syntax checks passed locally.

Live check summary: `/root/kdx-registration-live-validation.json`.
Initial private backup: `/var/backups/kdx-registration/initial-20261031` contains
PostgreSQL custom dump, role definitions, private configuration/signing key archive,
source upload, validation summary and checksums. Files are root-only; encrypt before
moving backups off-host. Restore guidance is in DEPLOYMENT.md.

## Remaining external checks

After the operator reported disabling firewalld, Caddy end-to-end checks from the
workstation succeeded: `http://172.12.2.82:8080/health` returned HTTP 200 and the
expected registration service/version; `/docs` returned HTTP 200; unauthenticated
`/api/v1/admin/devices` returned HTTP 401. No Caddy configuration changes were made
by the agent. The operator did not specify which host's firewall was disabled;
current firewall isolation must be rechecked before production use.

Temporary access without opening the API firewall more broadly:

```sh
ssh -N -L 13000:127.0.0.1:3000 root@172.12.2.77
# Open http://127.0.0.1:13000/docs on the workstation.
```

SELinux was Enforcing during the first environment inspection, but already
Permissive at the start of the authorized installation. The installer did not
change its mode. SELinux policy qualification with Enforcing remains outstanding;
firewalld stayed active throughout installation. The operator subsequently reported
disabling firewalld before the successful Caddy checks above.

The real `10000000000865DD` appliance was subsequently enrolled, approved and
activated under KronosDX Lab with a 30-day DEMO license, expiring 2026-11-30 at
22:19 Europe/Istanbul. The independent host agent and temporary workstation relay
are documented in `device-registration/DEPLOYMENT-20261031.md`. KVM licensing
enforcement, unattended network access, HTTPS/domain rollout and independent
security review remain outstanding. Chrony was installed on the registration VM
and NTP synchronization was verified during physical-device onboarding.

## Technical references

- PostgreSQL locks: https://www.postgresql.org/docs/current/explicit-locking.html
- FastAPI commit before response:
  https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/
- Ed25519: https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/

## Dashboard integration

The dedicated Dashboard was installed on `172.12.2.78:6000`, accessible through
existing Caddy `http://172.12.2.82:8081`. Authenticated read APIs and nested record
relationships were added without schema changes. All 24 Registration tests passed
on target PostgreSQL before deployment; real Dashboard sign-in and the existing
active device/customer/DEMO-license relationship were verified. See
`dashboard/DEPLOYMENT-20261031.md` in the repository for details.

## Subsequent verified WAN integration

The real device subsequently moved to `https://185.251.66.26:18444` using an
explicitly provisioned lab CA and normal certificate/IP verification. Its temporary
workstation relay was removed, and real reboot/automatic reauthentication passed
with unchanged customer/license binding. Public Dashboard TLS sign-in at
`https://185.251.66.26:18443` was verified; the existing gateway received the exact
HTTPS origin and Secure-cookie handling. Caddy/FortiGate/VPN configuration and
Registration schema were preserved. See
`device-registration/docs/WAN-ACCEPTANCE-20261031.md` for current evidence.
