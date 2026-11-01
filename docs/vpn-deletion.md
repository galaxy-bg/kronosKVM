# VPN deletion and fresh setup

This supersedes the earlier VPN archive/restore behavior in `central-vpn.md`.
Customer and licensing records are unaffected.

## Behavior

- **InfraBox → Delete VPN** immediately stops the local tunnel, disables autostart,
  removes the connection/profile, WireGuard private identity, public request and
  cached approval. A root-owned outbox retains only the old public request until
  the server acknowledges deletion. The independent registration signing key stays.
- **Dashboard → VPN → VPN kaydını sil** removes the exact peer from the live
  WireGuard interface, persistent configuration and managed registry. The VPN IP
  becomes available again. The device receives a signed deletion instruction and
  performs the same local cleanup on its next poll.
- A complete managed-peer removal on the VPN server is detected by device polling.
  Temporary SSH/telemetry failure, partial runtime/file drift and suspension are
  not interpreted as deletion. Historical archived server entries are cleaned up
  when their exact old device request reappears, even if its dashboard grant is gone.
- Polling is every 30 seconds. If either endpoint is offline, synchronization is
  eventual and the UI explicitly reports deletion pending; cleanup resumes when
  registration connectivity returns. Registration uses the existing WAN HTTPS
  route and does not depend on the tunnel being deleted.
- There is no Restore button or cached-approval restore endpoint. A new explicit
  **Request VPN access** generates a fresh WireGuard key and request UUID and
  requires a new administrator approval. A new setup is blocked while a local
  deletion acknowledgment is pending. The old VPN does not reconnect on its own.

Audit history and retired-generation tombstones stay in PostgreSQL; live VPN
configuration, IP reservation and device VPN secrets are deleted. Root-only
operational backups remain subject to the existing backup policy, with no UI
restore function. Other managed/unmanaged peers and licensing identity stay intact.

## Protocol and failure handling

Migration `0004` adds `vpn_deletions` with device/installation/key ownership,
public WireGuard key and request UUID. A stale poll or delete from a retired
request returns deletion for that generation; it cannot recreate the old grant
or delete a newer one. Reusing a retired WireGuard key is rejected. A new request
can replace a deleted VPN row only as PENDING with a fresh key; no authorization
is inherited.

VPN challenge input supports `vpn_operation: sync|delete` (default sync). The
operation is included in the signed challenge, in addition to the request hash.
`POST /api/v1/devices/vpn` accepts the matching `operation`. Changing sync to
delete after a signature was created is rejected. The response for a retired
request includes a ten-minute Ed25519-signed `kdx-infrabox-vpn-state` DELETED
document tied to the exact serial and public request. The host verifies its
signature, trust pin, request and validity before acting on remote deletion.

`POST /api/v1/admin/vpn/{id}/delete` requires administrator/CSRF protection via
the dashboard gateway and a reason. The legacy `archive` action is a compatibility
alias for deletion. Deleted grants are hidden from the normal VPN list and cannot
resume. `DELETE /api/v1/wireguard` and the existing Remote Assist profile deletion
both queue the same local host action. `/api/v1/wireguard/enroll` returns 410;
old cached approvals cannot be restored through it.

A remote operation is only acknowledged after the exact peer removal succeeds.
Failure leaves the outbox/grant retryable rather than reporting two-sided success.
The constrained manager supports idempotent delete and read-only inspect, using
the existing lock, backup and per-peer rollback. No `wg0` restart is needed.

## Deployment

Back up the database, all four component sources, VPN configuration/registry and
private device identities. Deploy the manager on `.74` first, then registration
migration `0004` and application on `.77`, dashboard gateway/build on `.78`, then
the device agent, host helpers and API/UI on the InfraBox. Preserve the restricted
SSH account/key and existing pinned trust configuration. Rebuild the appliance
images and launch with the existing hybrid startup helper to retain device access.
Enable `infrabox-central-vpn.timer` after acceptance checks.

The 2026-11-01 backups are `/var/backups/kdx-vpn-delete/20261101` on VPN and the
InfraBox, and `vpn-delete-20261101` under the registration/dashboard backup roots.
The registration dump retains all prior audit data. Do not roll back an old device
key into live use after deletion; validate with a fresh setup instead.

## Live acceptance — 2026-11-01

The real device's earlier server-side test deletion was propagated: its local
profile, WireGuard identity and cached approval disappeared and the old managed
registry entry was removed. Fresh key generation produced a new PENDING request
and separate administrator approval.

A second cycle deleted VPN locally. Before acknowledgment, the profile/key were
already absent and the public-only deletion outbox remained pending. After a
successful server call, the VPN list was empty and pending state cleared. A second
fresh key/request again required explicit approval. The registration identity
checksum remained unchanged. Final operation leaves the device connected with its
new key; the two unrelated VPN peers and `wg0` service lifetime are preserved.

309 appliance tests and 71 registration/dashboard/agent tests passed, with two
PostgreSQL-only concurrency tests skipped. Both browser suites and dashboard
production build passed. Migration 0004 matched the ORM schema. Deletion under a
simulated transport failure, replay, stale-generation requests and signed-document
tampering are covered without injecting outages into the live network.
