# Serial-based InfraBox identity

Retain the full 16-digit Raspberry Pi serial as device identity; generate the
hostname and KDX-iKVM SSID from its last eight characters, normalized to lowercase.
No manual `01/02` numbering or random fallback is used.

| Field | Example: first appliance |
| --- | --- |
| Serial | `100000008ed89866` |
| Hostname | `infrabox-8ed89866` |
| Wi-Fi SSID | `KDX-iKVM-8ed89866` |
| Initial Wi-Fi password | `KDX@8ed89866!` |
| Local name | `infrabox-8ed89866.local` |

The SSID is 17 ASCII bytes and hostname is 17 characters. Read the serial from
the kernel device tree, falling back to the Raspberry Pi `Serial` field in
`/proc/cpuinfo`. Missing/invalid/all-zero serials fail explicitly. Wi-Fi passwords are managed separately by the
[Wi-Fi password controller](wifi-password.md); custom passwords survive naming checks.

## Provisioning

Bootstrap generates the hostname; the legacy hostapd installer generates its
SSID from the same value. The container installer enables the identity service
before application startup. On boot it rechecks hardware, so a prepared SD card
moved to another Pi adopts the new board's serial-based names.

The controller supports existing NetworkManager wlan0 AP profiles and legacy
wlan0 hostapd. It retains profile UUID, security/passphrase, bridge, addresses
and routing policy. If no AP is provisioned at boot, it generates the hostname;
provision the AP and apply the command below afterward.

For existing boxes, use a verified Ethernet connection. Wi-Fi clients must
reconnect after the SSID changes:

```bash
cd /opt/kronoskvm
python3 scripts/device-identity.py
sudo python3 scripts/device-identity.py --apply --dry-run
sudo bash scripts/install-device-identity.sh
```

The installer enables the boot identity service and application dependency,
then recreates the API container with the host's name. No OS reboot is required.
Generated identity is recorded in `/etc/kronoskvm/device-identity.json`; Compose
`.env` is updated without removing unrelated keys. The old AP DNS alias is
retained. The full project files, including `scripts/management-ap.sh`, are required.

Existing TLS certificates/keys are retained. Fresh installations generate SANs
for the serial hostname and `.local` name. Existing trusted certificates need
normal reissuance with that name before trusted access via the new hostname;
the naming controller does not replace operator certificates.

## First appliance — 2026-10-08

Applied to `192.168.31.185`. OS/API hostname and actual radio SSID match the table
above. mDNS resolved the new name to `192.168.31.185`; AP DNS resolved it to
`192.168.34.100`. Ethernet IP remains unchanged. Chrome verified the new hostname,
admin login, active Wi-Fi and the retained disabled AP-access policy.

190 tests and lint passed: full-serial retention and short-name generation, missing hardware, dry-run
immutability, rollback on failed AP activation and boot without Ethernet.
Application containers and the identity service are healthy. Existing TLS/VPN
files and AP routing configuration matched their backup. Kutu2 has not yet been
migrated to these names.

- Full source/private-host backup:
  `/var/backups/kronoskvm/pre-device-identity-20261008.MzFloj`.
- Migration file/name backup: `/var/backups/kronoskvm/device-identity-9keox_jy`.

For rollback, first disable the identity boot service and remove the container
identity drop-in, otherwise boot reapplies the generated names. Restore backed-up
hostname/hosts/DNS/project settings, restore the AP SSID using saved profile UUID
metadata, then reload application containers. Keep private archives root-only.

The corrected short-name rollout is backed up at
`/var/backups/kronoskvm/short-identity.Tllv7j` (source) and
`/var/backups/kronoskvm/device-identity-_57qhsf3` (names/files).
