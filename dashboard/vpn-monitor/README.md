# Read-only WireGuard monitoring

Dashboard VPN view added 2026-11-01. The licensing/Evaluation workflow is deferred.
No Registration schema, customer/license data, VPN peer definitions, keys, routing,
FortiGate or Caddy settings are changed by this feature.

## Data flow

`VPN wg0 → root read-only collector → sanitized snapshot → restricted SSH reader →
Dashboard authenticated /api/vpn → React VPN tab`

The VPN VM is `172.12.2.74`; configured public endpoint is
`185.251.66.26:51820/UDP`. A new 30-second systemd timer queries only public
`wg show` selectors: interfaces, public-key, listen-port, peers, allowed-ips,
endpoints, latest-handshakes, transfer and persistent-keepalive. It never invokes
`dump`, private-key, preshared-keys, showconf, wg set or wg-quick actions.
It reads only the existing public peer registry, not wg0.conf contents.

Collector source is root-owned under `/opt/kdx-vpn-monitor`. Its unit is read-only
outside StateDirectory, limited to CAP_NET_ADMIN and AF_NETLINK/AF_UNIX, and runs
no network listener. Snapshot is `/var/lib/kdx-vpn-monitor/status.json`, root-owned,
group `kdx-vpn-reader`, mode 0640; parent directory is 0750.

The runtime Dashboard has no root password and no VPN administrative credential.
Its dedicated Ed25519 key remains on `.78` at
`/etc/kdx-dashboard/vpn-reader.key`, owned by kdx-dashboard, 0600. It is accepted
only from `.78`, with `restrict` and a forced `cat` command on the VPN server.
Arbitrary shell commands, PTY, forwarding, user rc and agent forwarding are
unavailable under that key. The reader account password is locked.

VPN SSH host identity is pinned, obtained through the existing authenticated root
session, with fingerprint:
`SHA256:ueCQ/zadkq6to9y/M4b4U70V9pCz+Q3UusBbIl5lRRo`.
The runtime uses StrictHostKeyChecking=yes, a dedicated known_hosts file, no SSH
agent, no password fallback, a fixed host/command and bounded connection time.
Do not replace a host key after an error without out-of-band verification.

The Dashboard revalidates the Registration credential by reading current device
inventory on every `/api/vpn` request before returning telemetry. A 15-second
internal telemetry cache does not bypass authentication. Readers/viewers may view;
there are no peer mutation endpoints. Incoming telemetry is parsed through an
explicit output allowlist; unknown fields, including private/PSK fields, are not
returned. Authentication tokens and SSH credentials are never in the response.

## Meaning of the fields

- A recent handshake is at most 180 seconds old. It is an observation, not a
  continuous connectivity guarantee or an active health probe.
- A zero handshake means none observed during the current interface/peer lifetime;
  it does not erase or disprove previous historical connections.
- Snapshots older than 90 seconds, transport errors and collection errors result in
  unknown status; stale observations are not presented as current online state.
- Traffic is from the **server** perspective: received is client→server; sent is
  server→client. Counters reset when WireGuard/interface/peer state resets; no
  historical billing or monthly usage is implied.
- Device association uses the hardware serial in the root-owned managed VPN peer
  registry against the Registration record. WireGuard and registration Ed25519 keys
  are distinct. This association is an inventory link, not proof of license validity,
  current physical ownership or cryptographic attestation.
- Unmanaged peers have no invented customer/hostname association. A missing registry
  is shown explicitly as a warning; live public metrics can still be displayed.

## Installed state and verification

Existing peers `.2`, `.10`, `.11` were preserved. Live HTTPS Dashboard validation
returned three peers, one recent handshake and one real-device match:
`10000000000865DD → KronosDX Lab → 10.77.0.11/32`.
Login/logout protection and the absence of private/PSK fields were verified.

22 Dashboard/gateway/collector tests passed. Chrome desktop/mobile fixture tests
passed VPN rendering, customer search, filtering, existing device details and all
previous Dashboard navigation/actions. Synthetic browser records do not alter live
registrations. The collector ran successfully on Rocky's Python 3.9; the gateway
runs under existing Python 3.11.

Live forced-command testing sent an innocuous alternate `echo` command and received
only the JSON snapshot, confirming it could not execute the requested command.

VPN configuration and registry SHA-256 hashes matched before/after installation.
The peer public-key list and `wg-quick@wg0` ActiveEnterTimestampMonotonic remained
identical (`3241927`); no VPN restart occurred. A pre-existing unrelated mcelog
failure was observed (start 2026-10-31 20:57:17); it was not modified. Both monitoring
and Dashboard services were healthy after deployment.

## Diagnostics

On VPN VM `.74`:

```sh
systemctl status kdx-vpn-monitor.timer --no-pager
systemctl show kdx-vpn-monitor.service -p Result -p ExecMainStatus
journalctl -u kdx-vpn-monitor.service -n 30 --no-pager
sha256sum -c /var/backups/kdx-vpn-monitor/initial-20261101/wireguard-before.sha256
systemctl show wg-quick@wg0 -p ActiveEnterTimestampMonotonic
```

On Dashboard VM `.78`:

```sh
runuser -u kdx-dashboard -- ssh -F /dev/null -T \
  -o BatchMode=yes -o IdentitiesOnly=yes -o IdentityAgent=none \
  -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile=/etc/kdx-dashboard/vpn-known-hosts \
  -i /etc/kdx-dashboard/vpn-reader.key kdx-vpn-reader@172.12.2.74 status
systemctl status kdx-dashboard --no-pager
```

Keep those commands internal. No new WAN SSH mapping or telemetry HTTP port is
needed. Public Dashboard remains `https://185.251.66.26:18443` using the existing
explicit lab CA trust; internal entry remains `http://172.12.2.82:8081`.

## Recovery

Dashboard pre-change source/config is under
`/var/backups/kdx-dashboard/pre-vpn-20261101`. VPN baseline hashes and peer list
are under `/var/backups/kdx-vpn-monitor/initial-20261101`. Runtime SSH private key
stays on the Dashboard and must never enter source archives or Git.

To stop monitoring, disable only `kdx-vpn-monitor.timer` and set
`KDX_DASHBOARD_VPN_MONITOR_ENABLED=false`, then restart the Dashboard. This does not
stop wg0. To revoke the read-only credential, remove only its forced-command key
from the dedicated reader account after review. Never restore a VPN configuration
or restart wg0 as part of rolling back this display-only feature.

## Central write operations

The read-only collector/key described above remains unchanged. New peer grants use a separate constrained account and service path; see [central VPN management](../../docs/central-vpn.md).
