# Validation and device simulator

From `registration-server/`:

```sh
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.lock
.venv/bin/python -m pytest -q
```

Fast SQLite tests cover workflow and cryptography; concurrency tests explicitly skip.
Use a dedicated disposable PostgreSQL database for complete validation. Tests drop
and recreate its schema, and require `test` in the database name. Never use live data.

```sh
docker run -d --name kdx-registration-test -p 127.0.0.1:55439:5432 \
  -e POSTGRES_USER=kdx_test -e POSTGRES_PASSWORD=disposable-test-only \
  -e POSTGRES_DB=kdx_registration_test postgres:16
# Wait until pg_isready succeeds:
docker exec kdx-registration-test pg_isready -U kdx_test
KDX_TEST_DATABASE_URL=postgresql+psycopg://kdx_test:disposable-test-only@127.0.0.1:55439/kdx_registration_test \
  .venv/bin/python -m pytest -q
docker stop kdx-registration-test
```

The suite covers new/pending identity, admin approval, valid/expired tokens, normal
authentication, copied SD/new serial, fresh SD/same serial, invalid signatures, replay,
expired/revoked licenses, unauthorized admin/viewer writes, concurrent duplicate
activation, concurrent enrollment and capacity, connection outage/grace/expiry,
license suspension/renewal/transfer, purpose/expiry, HTTPS enforcement and rate limiting.

## Simulator against Caddy

1. Create an identity and enroll it (creates only a pending record):

```sh
.venv/bin/python -m simulator.device identity --state ./device-a --serial 10000000ABC12345
.venv/bin/python -m simulator.device enroll --state ./device-a --serial 10000000ABC12345 \
  --url http://172.12.2.82:8080 --lab-http
```

2. In `/docs`, authorize with a securely retrieved administrator token. Create a
   customer, create a license, list devices, and approve the exact device ID,
   installation UUID and public key. Include an operator reason. Copy the one-time
   token using your secure handling process. Do not place it in shell history.
3. Obtain/pin the server public signing key via local `app.manage public-key`.

```sh
.venv/bin/python -m simulator.device activate --state ./device-a --serial 10000000ABC12345 \
  --url http://172.12.2.82:8080 --lab-http --server-public-key '<pinned-public-key>'
# The activation token is prompted without echo.
.venv/bin/python -m simulator.device authenticate --state ./device-a --serial 10000000ABC12345 \
  --url http://172.12.2.82:8080 --lab-http --server-public-key '<pinned-public-key>'
```

4. Clone test: copy `device-a` to a separate private test directory, authenticate
   with `--serial 10000000DEF67890`; expect HARDWARE_MISMATCH, unchanged original
   binding and an admin-visible audit event. Never use actual manufacturing keys.
5. Reinstall test: use a fresh state directory with the original serial; enroll;
   expect PENDING. Approval is rejected until an admin explicitly releases the
   current binding with `/reassign` and approves the replacement identity.
6. Outage test: after a successful online authorization with a pinned server key,
   use an unreachable test URL, e.g. `http://127.0.0.1:9`, for authenticate; expect
   `offline-grace` only before signed expiry. A fresh directory or denied/expired
   cache must fail. Do not stop production services to simulate the outage.
7. Revoke via the admin API, authenticate against the reachable server, and then
   repeat the outage test. The local denial flag must prevent offline activation.

The simulator stores private identity/cache files with mode 0600 in a 0700 directory.
Omit `--serial` on a real Raspberry Pi to read the OS hardware serial. This phase does
not install a first-boot agent or enforce licensing in the existing appliance UI.
