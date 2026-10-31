# Existing real InfraBox: verified WAN integration — 2026-10-31

This continues the deployed Registration Server, Dashboard and database. It does not
re-create applications, reset a database, delete devices, reissue the active license,
modify the SD image, or change FortiGate/WireGuard/Caddy configuration.

## Inspection and minimum changes

The physical device was already activated under the earlier supervised lab workflow:

| Binding | Existing value, preserved |
| --- | --- |
| Physical device | `infrabox-000865dd`, Ethernet `192.168.31.27` |
| OS hardware serial | `10000000000865DD` |
| Installation UUID | `c96d6174-2e02-4fc7-b065-6d27809d22f2` |
| Public device key | `xGcqAylcOo3w3ILJdPjqFDgtsC78m6NVvjq6rXcGwKY=` |
| Registration ID | `6998bfa8-3a28-4822-b290-ec1927cfa4b4` |
| Customer | `KronosDX Lab` |
| License ID | `36833f3a-fe4e-44d8-a956-681063c1bafe` |
| License | DEMO, expires **2026-11-30 22:19 Europe/Istanbul** |

Before this change the client used a workstation-dependent reverse SSH tunnel to
Caddy over lab HTTP and did not report registration into the appliance UI.

Changes are limited to:

1. The existing host agent supports an explicit CA certificate plus out-of-band
   SHA-256 fingerprint, retaining normal CA-chain and server-IP verification.
2. The existing client URL becomes `https://185.251.66.26:18444`; lab HTTP is disabled
   for this device. The pinned server Ed25519 signing key remains unchanged.
3. A separate allowlisted public status snapshot is published mode 0644 under
   `/var/lib/kdx-registration-public`; its directory is owned by the non-root agent.
   The private identity/cache stays in `/var/lib/kdx-registration` mode 0700/0600.
4. The existing API reads only that public directory through a read-only bind mount.
   `/api/v1/system/registration` remains behind existing web authentication; the
   pre-existing narrow loopback LCD identity can read it for diagnostics.
5. A read-only Settings → Registration & license card displays status, connection,
   hardware/installation/device/license IDs and signed offline-authorization deadline.
6. The existing Dashboard gateway accepts the new exact public HTTPS origin and
   marks that session cookie Secure. Existing internal HTTP lab access is preserved.
   No Dashboard frontend rebuild or database migration was required.

The endpoint names, schema, installed services and current records were inspected
before changes. New pending installations and original bindings already had proper
server-side checks; those mechanisms were reused.

## TLS trust and WAN path

Caddy's public root certificate was retrieved over authenticated SSH from
`/var/lib/caddy/.local/share/caddy/pki/authorities/local/root.crt`. No CA private key
was read or transferred. Its fingerprint was verified before provisioning:

```
27:B4:D3:BF:CF:CB:CB:FF:6E:22:51:32:84:74:50:DF:
D4:A9:24:B7:95:2E:19:24:04:52:08:07:E6:4F:E0:9E
```

Device trust is confined to the registration client configuration:
`/etc/kdx-registration-client/lab-ca.crt`. The system-wide CA store was not changed.
This is an explicitly provisioned lab CA, not a publicly trusted production PKI.
A standard browser needs this CA trusted separately before it can verify the public
Dashboard without warnings. A future public CA/domain migration must be deliberate.

Verified from the real appliance via its ordinary home gateway and Ethernet:

- Registration: `https://185.251.66.26:18444/health` → HTTP 200.
- Dashboard: `https://185.251.66.26:18443/` → HTTP 200.
- `ip route get 185.251.66.26` uses `192.168.31.1` through `eth0`, not WireGuard.
- Actual enroll/authenticate calls use verified TLS; no `-k`, CERT_NONE, disabled
  hostname checks or plaintext fallback is used by the client.
- The former workstation SSH reverse tunnel was explicitly stopped after successful
  direct authentication. The client no longer depends on the workstation.
- Public Dashboard sign-in, Secure/HttpOnly session cookie, inventory and logout
  were verified with the same trusted TLS anchor; original customer/license binding
  was read through that gateway.

## Acceptance matrix

| Requested test | Evidence / handling |
| --- | --- |
| 1. Read real Pi serial | OS device-tree serial is `10000000000865DD`; read each client invocation. |
| 2. Trusted transport | Explicit lab CA and IP verification; real WAN health/authentication passed. |
| 3. First enrollment | Existing audited real-device enrollment from earlier integration retained; PENDING behavior also covered by isolated integration tests. |
| 4. Dashboard appearance | Existing real hardware record visible and read through Dashboard gateway. |
| 5. Administrator approval | Original explicit approval event retained; no redundant approval or binding reset. |
| 6. DEMO activation | Original active 30-day DEMO and activation event retained; same license ID verified. |
| 7. Real hardware reboot | Performed as an explicit acceptance test; PASSED: boot ID changed; same private identity and fresh automatic WAN authorization observed. |
| 8. Reauthentication | Boot timer automatically runs the same identity; PASSED: boot ID changed; same private identity and fresh automatic WAN authorization observed. |
| 9. Correct association | Exact customer, device, installation, key and license IDs compared before/after. |
| 10. Server loss | A one-shot client request to closed `https://127.0.0.1:9` simulates transport failure without firewall/routing changes. |
| 11. Signed offline grace | Actual device returned ACTIVE/offline-grace from verified cache; normal online sync restored afterward. Invalid-CA errors instead deny and invalidate grace in automated tests. |
| 12. Non-destructive mismatch | Sent the existing public identity with synthetic serial `10000000DEF67890` to `/devices/challenge` over verified WAN TLS; server returned HARDWARE_MISMATCH and audited it. Real serial/state files were not changed. |

After the mismatch, the real original identity authenticated again successfully.
The original binding was never overwritten. Its Dashboard history intentionally
contains the test mismatch event; it is test evidence, not a second physical device.

A fresh UUID/key on a known serial still requires explicit re-enrollment/reassignment.
That recovery path is covered by existing isolated server tests; the live active
license was not revoked or reassigned merely for testing.

## Exact device diagnostics and recovery commands

On the Pi, use the current service account and persistent state:

```sh
sudo -u kdx-registration python3 /opt/kdx-registration-client/client.py identity
sudo -u kdx-registration python3 /opt/kdx-registration-client/client.py status
sudo systemctl start kdx-registration-client.service
sudo systemctl show kdx-registration-client.service -p Result -p ExecMainStatus
sudo systemctl list-timers kdx-registration-client.timer --no-pager
sudo journalctl -u kdx-registration-client.service -n 40 --no-pager
curl --cacert /etc/kdx-registration-client/lab-ca.crt \
  https://185.251.66.26:18444/health
```

Verify the provisioned CA independently with:

```sh
openssl x509 -in /etc/kdx-registration-client/lab-ca.crt \
  -noout -sha256 -fingerprint
```

For an approved certificate replacement, first verify the new fingerprint through
an authenticated out-of-band channel, install its public certificate as root, update
`ca_certificate_sha256` in the existing client config, and run the service. Never
repair a TLS problem by disabling verification or regenerating device identity.
Do not copy the private state off the device for these diagnostics.

## Exact Registration VM diagnostics

Run on `.77`; this keeps the administrator key in process memory and prints only
public device/license status:

```sh
cd /opt/kdx-registration
.venv/bin/python - <<'PY'
from pathlib import Path
import httpx, json
headers = {'Authorization': 'Bearer ' + Path('/root/kdx-registration-admin.token').read_text().strip()}
with httpx.Client(base_url='http://127.0.0.1:3000', headers=headers) as client:
    response = client.get('/api/v1/admin/devices/6998bfa8-3a28-4822-b290-ec1927cfa4b4')
    response.raise_for_status()
    value = response.json()
    print(json.dumps({k: value[k] for k in ('serial', 'status', 'customer', 'license', 'last_seen')}, indent=2))
PY
```

## Backups, validation and limits

Private device rollback archive and former images:
`/var/backups/kronoskvm/pre-wan-integration-20261031`,
`kronoskvm-api:pre-wan-integration-20261031`,
`kronoskvm-web:pre-wan-integration-20261031`.

The directory includes prior source, root-only private registration state,
pre-change identity/config checksums, initial boot ID and build logs. The private
identity checksum matched throughout the change; original `/etc/kronoskvm`
configuration hashes matched before reboot. Never publish the private archive.
Dashboard gateway/config backup: `/var/backups/kdx-dashboard/pre-wan-20261031`.

Local validation: 302 existing appliance/API tests, 14 agent integration/TLS tests,
11 Dashboard gateway/security tests passed. Chrome fixture tests covered ACTIVE
HTTPS, offline grace, mismatch, pending, mobile layout and safe text rendering.
Registration database/schema and server source were unchanged in this phase.

Offline documents remain limited to 24 hours by existing configuration and cannot
provide immediate disconnected revocation. Software keys and a reported Pi serial
are practical identity bindings, not hardware attestation. An attacker able to copy
keys and spoof the serial can evade software-only clone detection. Existing KVM
functions remain operational; this integration reports authorization, it does not
introduce new KVM feature restrictions.

Observed naming differs from the supplied infrastructure brief: the running AP SSID
is `KDX-iKVM-000865dd`, while the hostname is `infrabox-000865dd`. Both were preserved
as found; Wi-Fi/identity naming code and configuration were not changed.

## Final post-reboot evidence

- Boot ID changed from `a4aa097e-8fee-4db2-a3bf-ea6ad9700e46` to
  `bacfb1cd-85da-492f-8c50-1bfb890a1ec8`.
- Without manually starting the agent after boot, systemd recorded a successful
  start at 2026-10-31 23:38:15 Europe/Istanbul. Local API reported
  `ACTIVE / online / https`, authorized true, stale false.
- The exact private identity-file checksum remained unchanged. Device/customer/DEMO
  license IDs and license expiry remained unchanged; no new live identity was created.
- API, web and guacd containers were healthy; LCD, Witty Pi, Wi-Fi and registration
  timer were active; no failed systemd units remained. Physical panel visibility and
  interactive target HDMI/keypad operation were not operator-tested in this phase.
- Existing VPN autostart was false. Its normal boot helper switched its runtime
  enabled flag off on reboot. The pre-test active connection was restored using
  the existing profile and lifecycle helper; startup preference, keys, routes and
  server configuration were retained. All original `/etc/kronoskvm` file checksums
  then matched exactly, including the VPN configuration. VPN handshake and a ping
  to `10.77.0.1` succeeded afterward. This was runtime restoration, not new VPN
  configuration; license authentication continued independently through Ethernet WAN.

Device evidence: `acceptance-post-reboot.json`, `identity-before.sha256`, and
`config-after-reboot-restored.log` under the protected pre-change backup directory.
Central evidence: `/root/kdx-wan-real-device-acceptance-20261031.json` on `.77`.

The boot-time WAN reauthentication succeeded while the old VPN interface was still
down under its existing autostart preference. This directly demonstrates that
registration no longer depends on either WireGuard or the workstation relay.
