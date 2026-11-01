# Central VPN management with device keys

Implemented 2026-11-01. **VPN deletion now synchronizes both endpoints and requires fresh setup; see [the current deletion workflow](vpn-deletion.md).** The archive/restore details below describe the earlier implementation. No VPN-server SSH username or password is entered on an
InfraBox. Registration identity (Ed25519) and tunnel identity (WireGuard) are
separate keys and remain on the device. VPN access is independent of license
expiry and does not add any appliance login restriction.

## Operator flow

1. On the InfraBox, open Settings → WireGuard VPN → **Request VPN access**.
2. The host creates/reuses its WireGuard identity. Its registration agent proves
   possession of its own Ed25519 identity over verified HTTPS. A PENDING VPN
   request contains only the public WireGuard request.
3. In Dashboard → VPN → **VPN erişim yönetimi**, verify the serial/public key and
   approve with a reason. Allocation is automatic. An exact existing managed peer
   is adopted without changing its IP/key or restarting its tunnel.
4. The device polls every 30 seconds. The registration server signs the approved
   public configuration, valid for ten minutes. The host verifies this signature,
   the pinned server key, serial and exact local WireGuard request before using it.
5. The initial explicitly requested connection is attempted once. The bridge does
   not override later Disconnect or the existing autostart setting. Deleting the
   local profile cancels central polling until explicitly requested again.

Dashboard supports **approve**, **disable**, **enable**, and **archive**. Disable
removes the selected peer from persistent and runtime configuration, retaining its
metadata and reserved IP. Enable reinstates that exact peer/IP. Archive also keeps
history and IP reservation; archived grants cannot silently reactivate. Changed
keys/installations or archived-grant replacement currently require operator
recovery; there is no automatic key takeover or rotation in this release. Manually
configured peers outside the managed registry are not writable through this UI.

Existing local manual import and cached-public-profile restore remain available.
The browser password endpoints return HTTP 410; the old SSH enrollment endpoint
only permits restoration from a cached public response. Password transport code is
retained solely for historical/CLI compatibility and is not called by these APIs.

## Trust and privilege separation

- The device signs a single-use, expiring challenge whose purpose is `vpn` and
  whose message includes SHA-256 of the canonical public WireGuard request. A
  proof cannot be reused for activation or a different key/request.
- Registration retains one VPN grant per device, tied to its exact installation
  and Ed25519 key. A new installation cannot overwrite that grant.
- Registration VM `.77` uses `/etc/kdx-registration/vpn-manager.key` to connect as
  **kdx-vpn-manager**, not root, to `.74`. The private SSH key is generated on `.77`
  and stays there. Host verification is mandatory, with no password fallback.
- On `.74`, root-owned `authorized_keys` allows that key only from `.77`, with
  forwarding/PTY disabled and a forced fixed command. A no-argument sudo rule
  permits only `/usr/local/sbin/kdx-vpn-manage.py`. Local privilege is needed for
  WireGuard; no remote root shell is exposed by this account.
- The forced helper validates a bounded JSON envelope and exact peer identity.
  It reuses the existing locked allocation/backup/rollback code and `wg set` for
  one peer, without restarting `wg0`. Other peer blocks and private keys stay intact.
- Existing `.78` read-only monitoring credentials keep their original permissions.
  Dashboard mutations use its existing administrator session and CSRF protection;
  it does not hold the VPN management SSH key or private tunnel keys.

## Deployment

Back up registration PostgreSQL and source, dashboard source, the device source
and identities, and VPN `wg0.conf` / public peer registry before an upgrade.

On the VPN VM install `scripts/kdx-vpn-manage.py` alongside the existing root-owned
`/usr/local/sbin/kdx-wg-server.py`. Keep `/etc/wireguard/kdx-registration.json` as
the fixed source of endpoint, pool and interface configuration. Create a
password-locked `kdx-vpn-manager` system account, root-owned home and `.ssh`
directory, and a root-owned authorized key with these restrictions:

```
from="172.12.2.77",restrict,command="/usr/bin/sudo -n /usr/local/sbin/kdx-vpn-manage.py" ssh-ed25519 <PUBLIC_KEY_FROM_REGISTRATION_VM>
```

The sudoers rule is deliberately restricted to no command arguments; validate
with `visudo -cf` before use:

```
kdx-vpn-manager ALL=(root) NOPASSWD: /usr/local/sbin/kdx-vpn-manage.py ""
```

Generate the dedicated Ed25519 SSH key on `.77`, owned by kdx-registration (0600).
Provision the VPN host's independently verified public host key into the fixed
known_hosts file. Set `KDX_VPN_MANAGEMENT_ENABLED=true` in the existing protected
registration environment, deploy the new modules and run `alembic upgrade head`
(migration `0003`). Default paths are `/etc/kdx-registration/vpn-manager.key` and
`/etc/kdx-registration/vpn-known-hosts`. Never copy a private key into this repository.

Deploy the new dashboard gateway/frontend using `deploy/publish_static.py`. On the
InfraBox update `device-registration/client.py`, the host scripts and API/UI; use
the existing hybrid startup helper after rebuilding the API/web images. Do not
replace the API's device mounts/cgroup policy with a generic Compose recreation.
Install `deploy/systemd/infrabox-central-vpn.{service,timer}`. The host bridge
requires the existing registration config to be root-owned and not writable by
service users, with the existing pinned server signing key. The timer is inert
until Request VPN access creates the root-owned opt-in marker.

Backups for this deployment are under `central-vpn-20261101` on registration and
dashboard; `/var/backups/kdx-vpn-central/20261101` on VPN;
`/var/backups/kdx-central-vpn/20261101` on the InfraBox. PostgreSQL migrations are
additive; rollback application source separately and preserve identities/audit.
After an unconfirmed remote operation, repeat the same action to reconcile; do
not mark it successful or bypass identity checks. SSH operations and PostgreSQL
are not a distributed atomic transaction; exact-state retries are idempotent.

## Acceptance

The real serial `10000000000865DD` requested PENDING using its device signature.
WAN HTTPS dashboard approval, disable and enable succeeded and retained
`10.77.0.11/32` and the existing public key. The `.2` and `.10` peers, unrelated
configuration and original registry fields were preserved. The WireGuard service
start timestamp remained `3241927`; no `wg0` restart occurred. Its two new audit
state changes may reset the selected peer's handshake/traffic counters.

The archived-grant path, rollback and malicious proof tests use synthetic fixtures;
the real device was not archived. A forced-command SSH probe with an alternate
shell command failed safely rather than executing it. Browser tests verify the
absence of username/password fields, device-key requests, dashboard approval and
mobile layouts. Server signing, request-binding, replay, role/CSRF and TLS tests
run locally without using production test data.

Validation totals: 307 appliance tests and 68 registration/dashboard/agent tests
passed; two disposable-PostgreSQL concurrency tests were skipped. Both browser
suites and the dashboard production build passed. Migration 0003 applied and
Alembic model/schema comparison reported no pending changes.
