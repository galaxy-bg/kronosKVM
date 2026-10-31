# KDX InfraBox Registration and Licensing Server

Independent FastAPI service for the Registration VM (`172.12.2.77:3000`).
Lab entry point: `http://172.12.2.82:8080`. No dashboard frontend, WireGuard,
Caddy or appliance networking changes are included.

## Layout

- `app/models.py`: SQLAlchemy schema and binding constraints.
- `app/schemas.py`: strict request validation; clients cannot supply status.
- `app/main.py`: HTTP API, state transitions, authorization and audit events.
- `app/crypto.py`: Ed25519 proof/document helpers.
- `app/manage.py`: local administrator and signing-key lifecycle.
- `migrations/`: immutable initial schema and additive management migration `0002`.
- `simulator/device.py`: virtual identities, actual Pi serial discovery, offline grace.
- `tests/`: workflow, security, PostgreSQL concurrency and outage coverage.
- `deploy/`: Rocky Linux installer and restricted systemd units.

See [API](docs/API.md), [deployment](docs/DEPLOYMENT.md),
[security](docs/SECURITY.md), and [testing](docs/TESTING.md).

## Protocol

1. Device reads its hardware serial from device tree/CPU info and loads or generates
   an installation UUID and Ed25519 private key. The key stays local (0600).
2. `enroll` sends only the public identity, model and firmware. A new identity is PENDING.
3. An authenticated administrator creates a customer/license and approves an exact
   serial/installation/public-key binding. The returned token is shown once, hashed
   in PostgreSQL, expires and can perform one activation.
4. Device obtains an activation-purpose challenge, signs its exact UTF-8 message,
   and submits the signature and token. The server binds and activates transactionally.
5. Normal boots use fresh authentication-purpose challenges. Active devices receive
   a short bearer session and an Ed25519-signed, identity-bound grace document.
6. A different serial with copied UUID/key is rejected as HARDWARE_MISMATCH and
   audited without changing the original binding. Reinstallation remains pending
   until explicit administrator release and approval of the new identity.

PostgreSQL uniqueness and partial indexes prevent duplicate current installations,
current keys, public keys and device/license bindings. A transaction advisory lock
serializes state operations across processes for this initial deployment; license
capacity checks and token consumption are atomic. HTTP retries with a fresh proof
can retrieve the result of a consumed token only while the original approved binding
is still active. A used token cannot activate another device or resurrect a released
identity. Every challenge is single-use, expires, and is purpose/audience bound.

The SSID returned by this service is `infrabox-<last eight uppercase serial characters>`.
It is informational; this service does not modify the existing appliance's Wi-Fi.

## Quick local tests

```sh
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.lock
.venv/bin/python -m pytest -q
```

SQLite provides fast unit coverage; concurrency tests explicitly require disposable
PostgreSQL. See the testing guide for exact commands. Do not point tests at a live
registration database.

Customer/device contact metadata and reversible archival: see [management API](docs/API.md#customer-and-device-management) and [current infrastructure status](../docs/infrastructure-management.md).
