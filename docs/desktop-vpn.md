# PC and Mac VPN clients

The dashboard creates separate WireGuard peers for Windows, macOS, Linux and other
computers. Desktop records are separate from InfraBox hardware identities and
licensing. Each computer gets its own key and an automatically allocated VPN IP.

## Operator workflow

1. Sign in as an administrator through the HTTPS dashboard, open **VPN →
   Bilgisayar VPN istemcileri → Bilgisayar ekle**.
2. Enter the computer name/platform and optional owner, email and customer.
3. Select **Oluştur ve dosyayı hazırla**. The browser generates X25519 keys and
   submits only its public key and metadata. The explicit administrator action
   registers the peer on the existing server.
4. Select **.conf dosyasını indir** in the same window. Open WireGuard on the
   target computer and choose its import-from-file option, then activate the tunnel.
5. Use **Erişimi kapat / Erişimi aç / Bilgisayarı sil** in the client list.

The private key never enters the registration service, gateway, PostgreSQL,
localStorage or sessionStorage. The generated configuration stays in component
memory until download/close/logout/unmount. The Blob URL is revoked after download.
There is no permanent download or private-key recovery endpoint. Save the downloaded
file privately; if it is lost, delete that client and create a fresh one.

Key generation requires a secure browser context and X25519 support; unsupported
browsers receive an explicit message before an API request is sent. Use the HTTPS
lab endpoint `https://185.251.66.26:18443` with the provisioned lab CA trusted.
Plain internal HTTP cannot generate these keys. Localhost is supported for tests.

A failed/uncertain network operation can be retried in the same dialog with the
same public key/UUID. The key and request stay only in that dialog. Closing it
loses the private key; an unconfirmed PENDING record remains visible for cleanup.
Reusing a UUID with different metadata/key, reactivating a deleted record, or
reusing an old client key is rejected. No second peer/IP is allocated on retry.

## Access meaning

ACTIVE / **Erişim açık** means server permission, not a proven connection. Shared
VPN telemetry shows handshake age/traffic separately and matches clients by public
key. Suspension removes only that peer from runtime/persistent configuration while
retaining its IP. Deletion removes the peer and registry reservation, retaining
public audit history; its IP can be allocated again. A desktop has no management
agent, so deleting it centrally does not erase its local `.conf` file. The user
must remove that file from their computer; the old key no longer connects.

The generated profile uses only the existing private VPN subnet, not a default
route, DNS override or customer-LAN route. Customer assignment is inventory
metadata, not customer isolation. A desktop with access to the shared VPN can
reach other allowed peers in that VPN. Existing forwarding policy applies.
InfraBox license expiry does not control desktop VPN permission.

## Implementation

- `registration-server/app/models.py`: public-only `VpnClient` model.
- Migration `0005`: additive desktop-client table, independent of device records.
- `/api/v1/admin/vpn-clients`: authenticated GET and administrator POST.
- `/api/v1/admin/vpn-clients/{id}/{suspend|resume|delete}`: administrator + reason.
- Dashboard `/api/vpn/clients` and `/api/actions/vpn-clients/...`: existing session,
  Origin and CSRF checks; viewer mutation is denied.
- `dashboard/frontend/src/vpnConfig.js`: browser X25519 keys and strict `.conf`
  rendering; validates binding, private-only IPv4 routes and profile fields.
- `VpnClients.jsx`: one-time download, create/retry dialog and lifecycle controls.
- Constrained server protocol version 2 identifies a desktop by UUID (`client_id`),
  without inventing a hardware serial. Version 1 device enrollment is preserved.
  Both share the existing locked allocator and per-peer rollback transactions.

No desktop private-key endpoint exists. HTTP responses are `no-store`; API logs
contain request path/status, not bodies or keys. Only public request metadata goes
to the fixed key-only SSH manager on `.74`. No remote root login or password is
used by the product flow, and no tunnel/interface restart is needed.

## Deployment

Back up registration PostgreSQL, registration/dashboard sources and the VPN
configuration/registry. Upgrade `/usr/local/sbin/kdx-wg-server.py` on `.74` first
(version 2 public-request validation and mixed peer allocation), then registration
models/schemas/API plus `alembic upgrade head` to `0005`, then the dashboard gateway
and frontend. Publish built files with `dashboard/deploy/publish_static.py` to
preserve service-user readability. Existing account keys and trust pins stay intact.
No appliance source or routing/firewall change is required for this feature.

2026-11-01 backups: `/var/backups/kdx-desktop-vpn/20261101` on `.74`,
`/var/backups/kdx-registration/desktop-vpn-20261101` on `.77` and
`/var/backups/kdx-dashboard/desktop-vpn-20261101` on `.78`.

## References

- [WireGuard quick start and key format](https://www.wireguard.com/quickstart/).
- [W3C Web Cryptography X25519 operations](https://www.w3.org/TR/webcrypto/#x25519).
- [WireGuard namespace integration](https://www.wireguard.com/netns/) for the
  isolated live acceptance client; no production appliance route is replaced.

## Acceptance — 2026-11-01

310 appliance tests and 75 registration/dashboard/agent tests passed; two
PostgreSQL-only concurrency tests were skipped. Two JavaScript crypto/config tests
passed, including independent OpenSSL derivation of the browser-generated public
key and rejection of injected directives/default routes. Browser smoke tests
performed actual key generation and a real .conf download, verified no private
key appeared in API bodies, then deleted the synthetic client. The production
frontend build and migration/ORM comparison passed.

A temporary live desktop peer received `10.77.0.12/32`. An isolated WireGuard
namespace acted as a separate computer and reached both the VPN server and
InfraBox HTTPS at `10.77.0.11`. Suspension blocked its HTTP access; resume restored
it. Telemetry matched that peer to its desktop record instead of inventing an
InfraBox identity. The temporary peer/namespace/key were removed after acceptance.
The appliance's actual VPN identity and original peers were preserved; no
forwarding, firewall, Caddy, FortiGate or existing VPN-interface restart was needed.
This validates the standard WireGuard configuration and server path, not a native
Windows/macOS application automation run on the user's computer.
