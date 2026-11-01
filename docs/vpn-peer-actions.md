# Actions from the live VPN peer table

Administrators can use **VPN → VPN eşleri → İşlemler → Sil** for either a
registered client/device or an old manually configured peer. The confirmation
shows its exact public key and VPN addresses, requires typing the displayed
address(es), and requires an operator reason. Viewers have no mutation controls.
Deletion is disabled when current telemetry is unavailable/stale.

No live peer is selected by IP alone. The request contains its public key and
expected canonical private IPv4 /32 address set. A changed address set is rejected.
A delayed deletion for an old key cannot remove another key that later reused its
IP. Successful deletion drops only that peer from persistent and live state;
the VPN interface is not restarted and root-only backups/rollback are preserved.

## Dispatch

- `POST /api/vpn/peers/delete` uses the existing dashboard admin session, Origin and
  CSRF protection, forwarding to `/api/v1/admin/vpn-peers/delete`.
- A known InfraBox public key uses its normal grant deletion/tombstone and signed
  local-cleanup flow. Its profile is cleared at the next online synchronization.
- A known desktop public key uses desktop deletion, retaining public audit history
  and releasing its IP. The user removes their local file manually.
- An unknown key uses the constrained manager's `delete-unmanaged` operation. Its
  bounded version-3 public envelope has only `public_key` and `allowed_ips`.
  Under the existing server lock, the manager refuses keys in its managed registry,
  validates exact file/runtime addresses in the configured VPN subnet, rejects the
  server's own identity, and removes the selected peer transactionally. A managed
  peer with missing central metadata requires reconciliation instead of bypassing
  its lifecycle. Manual peers without /32 VPN address selections are not supported.

The registration service records actor/key/address/reason in the audit log. The
read-only monitor key retains its old permissions; all writes use the separate
constrained service account. After a successful delete the gateway suppresses
older telemetry samples of that key for up to 90 seconds and adjusts table totals.
A newer sample reporting a legitimately re-added key is not hidden.

## Validation / deployment

Unit tests cover unmanaged-only deletion, route drift, rollback, key/IP reuse,
managed desktop and InfraBox lifecycle dispatch, admin/CSRF checks and stale-sample
suppression. Browser tests cover wrong IP confirmation, cancellation, the exact
selected payload, post-delete refresh and mobile layout. No real legacy peer was
deleted during browser testing.

Deploy the constrained manager, registration API/schema and dashboard gateway/UI
in that order. No database migration, WireGuard restart or firewall change is
needed. Source and VPN backups for this change are under
`/var/backups/kdx-peer-actions/20261101` on the VPN VM,
`/var/backups/kdx-registration/peer-actions-20261101` on registration and
`/var/backups/kdx-dashboard/peer-actions-20261101` on dashboard.

The live acceptance test creates a temporary unmanaged peer and removes only that
selection through WAN HTTPS dashboard/API. The original `.2`, `.10`, `.11` and
`.12` peers remain for the operator to manage explicitly. This feature does not
identify a manual peer's computer name from its IP or handshake alone.
