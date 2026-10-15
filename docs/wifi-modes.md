# Wi-Fi AP modes

Open **Settings → Wi-Fi access point → Wi-Fi mode**, choose a mode and select
**Apply Wi-Fi mode**. The appliance uses one band at a time, keeping the same
SSID, password, bridge, DHCP/DNS and customer-network routing policy.

| Mode | Band | Channel | NetworkManager channel width |
| --- | --- | --- | --- |
| Standard (default) | 2.4 GHz | 6 | 20 MHz |
| Performance | 5 GHz | 36 | 80 MHz when supported |

The radio/driver decides which channel width it can actually activate. Settings
shows the actual frequency, channel and width. The selected mode survives boot
and password changes. Upgrades without a saved mode start with Standard.

The helper checks that channel 36 is available under the current device country
settings. It does not override the country or activate disabled/radar channels.
If 5 GHz activation fails or the radio remains on the wrong band, it starts
Standard and saves Standard, with a visible fallback message. If recovery also
fails, it restores the previous profile and credentials.

Switching briefly disconnects Wi-Fi clients; reconnect to the same SSID with the
same password. Standard offers broader coverage; Performance can improve local
transfer speed under suitable radio conditions. Range and transfer speed depend on the assembled enclosure and client laptop;
see the initial field observations below.

NetworkManager's band/channel/width settings are documented in the
[official wireless settings reference](https://www.networkmanager.dev/docs/api/latest/nm-settings-nmcli.html).

## First appliance verification — 2026-10-09

Deployed to `192.168.31.185`. Real Chrome exercised Standard → Performance →
Standard through Settings. Performance radio status reported 5200 MHz / 80 MHz;
Standard reported 2437 MHz / 20 MHz. The driver selected primary channel 40 for
the 80 MHz transmission despite the profile requesting channel 36. Settings
shows the actual radio channel. SSID, default/custom password status and
customer-network routing policy were retained across both transitions.

The final saved mode is Standard. Re-running the boot helper preserved Standard.
Unit tests verify Performance persistence across boot-helper execution/password
changes and Standard recovery after unsupported, failed or wrong-band 5 GHz
activation. `make check`: 210 tests passed. No full OS reboot, distance test or
throughput measurement was performed.

Backup: `/var/backups/kronoskvm/pre-wifi-modes.mSZWmv` (root-only).
Previous images: `kronoskvm-api:pre-wifi-modes-20261008` and
`kronoskvm-web:pre-wifi-modes-20261008`. New API/web images use tag
`wifi-modes-20261008` and `dev`; the final web image is `wifi-modes-20261008-ui`. The host helper
also activates an unchanged saved profile if the AP radio is not ready at boot.
Deployment ran in a transient systemd service
so AP reconnects could not interrupt it. A temporary test timer restored Standard
successfully and is not part of normal appliance operation.

## User-reported field observations — 2026-10-09

With Performance enabled, the user reported a 13 GB ISO upload in progress from
approximately five metres away in the same room, with a noticeable improvement
compared with 2.4 GHz. Connectivity remained stable through a wall at distances
up to approximately ten metres. Upload completion time and a measured transfer
rate were not provided, so these observations are not a throughput benchmark.

Keep Standard (2.4 GHz) as the default, Performance (5 GHz) as an option, and
wired 1 Gbps Ethernet as the alternative when wireless conditions cause trouble.
