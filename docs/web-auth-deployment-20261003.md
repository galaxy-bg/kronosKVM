# Web authentication deployment — 2026-10-03

Deployed the local authentication worktree (based on commit `3134c0e`) to
`192.168.31.185`, under `/opt/kronoskvm`. ARM64 API/web images were rebuilt and
activated through `systemctl reload kronoskvm-containers.service`. No appliance
reboot or OS update was performed.

## Recovery artifacts

- Application backup: `/var/backups/kronoskvm/pre-web-auth-20261003.paGqB4/application`
- Previous API image: `kronoskvm-api:pre-web-auth-20261003`
- Previous web image: `kronoskvm-web:pre-web-auth-20261003`

For rollback, restore the backed-up application files, retag both previous
images as their respective `:dev` images, then reload the container service.
Keep the post-deployment authentication file private; it is outside the source
backup. The older application does not enforce web authentication.

## Validation

- All 130 local tests and lint passed before deployment.
- The new API image passed an isolated authentication/password-change smoke test
  on the appliance's ARM64 Python 3.9 runtime, using temporary test credentials.
- Both production containers became healthy; no failed systemd units were found.
- HTTP management requests redirect to HTTPS (308); gateway health remains public.
- Anonymous system/service APIs return 401. First login returns a Secure,
  HttpOnly session cookie and requires password replacement; management access
  remains blocked (403) until that replacement.
- Chrome verified the live login page at desktop/mobile sizes and the mandatory
  password-change screen. Test sessions were logged out.
- The real administrator password was not changed during validation. The initial
  `admin` / `ChangeMe` login is retained for the operator's first password setup.
- `/var/lib/kronoskvm/state/web-auth.json` has mode 0600 and owner 10001:20.
- After deployment, RAM use was approximately 513 MiB, available memory 3282 MiB,
  with no swap use. This was not a video/VPN load test.

See [web authentication](web-authentication.md) for session lifetime, storage,
password recovery and the boundaries of the management authentication policy.

## Later update: optional password replacement

At the operator's request, default-password replacement was made optional.
`admin` / `ChangeMe` opens management immediately on a fresh installation;
existing chosen passwords are preserved. Legacy first-login flags no longer
restrict access. All 131 local tests passed, and the updated ARM64 image passed
an isolated default-login/legacy-flag test. The production password was not reset;
a live `ChangeMe` attempt returned 401 because it is no longer the current
credential. This does not indicate a required-password-change screen.

Backup before this update:
`/var/backups/kronoskvm/pre-optional-password-20261003.jiMs2N/application`.
Previous image tags: `kronoskvm-api:pre-optional-password-20261003` and
`kronoskvm-web:pre-optional-password-20261003`.
The API was updated through a small image layer copying the changed auth module
onto the previous validated image; dependency versions were preserved. The web
image was rebuilt using the repository's Dockerfile with host networking.

Host SSH access policy was only inspected, not modified. Password authentication
is enabled; `kronosdx` has a shell and the recovery service user has nologin.
A shared default web administrator does not establish zero trust or separate
customer permissions from owner administration. Identifying customer host access
and defining separate web permissions is required before claiming OS isolation.
