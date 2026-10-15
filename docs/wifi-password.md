# Wi-Fi access-point password

Every InfraBox uses `KDX-iKVM-<last 8 serial characters>` as its management SSID.
Its initial WPA2 password is `KDX@<last 8 serial characters>!`, using lowercase
hexadecimal from the Raspberry Pi serial printed on the appliance label.

For serial `100000008ed89866`:

- SSID: `KDX-iKVM-8ed89866`
- Initial password: `KDX@8ed89866!`
- Management URL: `https://192.168.34.100`

Sign in as administrator, open **Settings → Wi-Fi access point**, enter the new
password twice, and select **Change Wi-Fi password**. Passwords accept 8–63
printable ASCII characters. The status indicates default or custom password use;
custom passwords are never returned by the API. The administrator login password
is separate from the Wi-Fi password. The same Settings section also offers
[Standard (2.4 GHz) and Performance (5 GHz) modes](wifi-modes.md).

Changing the password reconnects the AP and disconnects Wi-Fi clients. Reconnect
with the new password. Ethernet management remains available. Customer-network
routing settings, bridge membership, DHCP/DNS and Ethernet configuration are retained.

## Installation and persistence

After serial identity provisioning and creation of a persistent wlan0 AP profile:

```sh
sudo bash /opt/kronoskvm/scripts/install-wifi-password.sh
```

The container installer also installs this controller. The root helper supports
NetworkManager keyfiles and legacy wlan0 hostapd. An existing protected AP is
adopted instead of resetting its password. An open AP receives the serial-based
default. WPA2/RSN uses CCMP. NetworkManager and hostapd receive a derived PSK
through root-only files; passwords are not passed in command arguments.

`/etc/kronoskvm/wifi-ap.json` stores the selected password, root-only (0600).
The boot service runs after serial identity provisioning, before containers.
A custom password survives boot and repeated installation. A device still using
the default derives the default from its current board serial if its SD card is
moved. Password changes roll back the previous AP configuration if activation fails.

The authenticated API queues a bounded, private (0600) request under the shared
state directory. A systemd path unit consumes it; a timer refreshes public status.
Request identifiers let the UI distinguish completion from periodic status refresh.
API validation errors and status do not include password values.

Only the first appliance is updated by this change; the office appliance requires
its own deployment.

## First appliance verification — 2026-10-08

Deployed to `192.168.31.185` with SSID `KDX-iKVM-8ed89866` and final password
`KDX@8ed89866!`. NetworkManager reports `wpa-psk`, `rsn`, `ccmp` and connected
wlan0; the Wi-Fi boot/action/status services, DNS and Avahi are active.
API and web health checks pass.

Validation: `make check` passed all 205 tests. Real Chrome tested mismatched
confirmation, a successful custom password change, cleared fields, unchanged
customer-network routing policy and final restoration of the default. Re-running
the boot helper preserved the custom password and subsequently the default.
No full OS reboot or separate client password association test was performed.

Rollback source/private host backup:
`/var/backups/kronoskvm/pre-wifi-password.FmQCbc` (root-only).
Previous images: `kronoskvm-api:pre-wifi-password-20261008` and
`kronoskvm-web:pre-wifi-password-20261008`. New API image:
`kronoskvm-api:wifi-password-20261008`; final web image:
`kronoskvm-web:wifi-password-20261008-ui` (also tagged `dev`).
