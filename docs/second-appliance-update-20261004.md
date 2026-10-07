# Second appliance update — 2026-10-04

Updated `192.168.1.107` (`kdx-infrabox`, aarch64) under `/opt/kronoskvm` with
the current application worktree. The update includes administrator
authentication and CLI reset, the admin account menu, and appliance-side browser
Telnet/RDP/VNC connections. No reboot or OS update was performed.

## Recovery

- Backup directory: `/var/backups/kronoskvm/pre-office-update-20261004.W8DRO0`.
- Application backup: `application.tar.gz` in that directory.
- Private device configuration/state backup: `private-state-config.tar.gz`.
  Keep this root-only archive private; it contains device-specific configuration.
- Previous API image: `kronoskvm-api:pre-office-update-20261004`.
- Previous web image: `kronoskvm-web:pre-office-update-20261004`.
- Updated images: `kronoskvm-api:office-update-20261004` and
  `kronoskvm-web:office-update-20261004`, also tagged `:dev`.

For rollback, restore the application archive into `/opt/kronoskvm`, tag the
previous API/web images as `:dev`, then reload
`kronoskvm-containers.service` and remove `kronoskvm-guacd`. Restoring the older
application removes management authentication enforcement. Do not restore the
private state archive unless a device configuration/state rollback is intended.

## Validation

- The newly built ARM64 API image passed an isolated default-login, session and
  remote-route/framing smoke test. The web image passed `nginx -t`.
- API, web and guacd containers became healthy; no failed systemd units remained.
- API listens on `127.0.0.1:8000`; guacd listens on `127.0.0.1:4822`.
- Anonymous management API requests return 401. Live HTTPS login with
  `admin` / `ChangeMe` succeeds, with optional password replacement. Test
  sessions were logged out; the administrator password was not changed.
- The authentication state file has mode 0600 and owner 10001:20.
  `/usr/local/sbin/infrabox-reset-admin` is installed as root with mode 0755.
  The helper was not run against the real credentials.
- Served authentication, dashboard, browser-connection and Guacamole JavaScript
  hashes match the local implementation. The API badge is absent and account
  actions are under the admin menu.
- Real Chrome verified default login, Dashboard, the admin menu, browser
  connection choices and logout, with no page errors.
- Device configuration, TLS files and the existing connection registry matched
  their pre-update backup byte-for-byte.

Real RDP target login remains pending. See
[browser connections](browser-connections.md) for isolated Telnet/VNC and browser
validation and feature limits. HDMI/HID, RTC and VPN qualification status is not
changed by this application update.

## LCD recovery after power cycle

The LCD runner initially exited successfully without drawing because this
physically equipped unit had no `/etc/kronoskvm/lcd.enabled` marker. The marker
was created, the repository's guarded keypad drop-in installed, and network
ordering replaced with local-filesystem/module ordering so the splash does not
wait for networking. The service was restarted; a power-cycle check by the
operator remains pending. This does not add hardware backlight control.

Previous drop-in backup:
`/var/backups/kronoskvm/lcd-enable-20261004.RM8BFB/keypad.conf`.

## LCD backlight control

The operator confirmed BL is connected to physical pin 18 (BCM24), and driving
BCM24 low turns the light off. Installed the opt-in BCM24 backlight drop-in and
updated the LCD renderer: BL stays off while the panel initializes and turns on
only after the splash frame is written. Added `gpio=24=op,dl` under `[all]` in
`/boot/firmware/config.txt` for the next boot. The service stop hook drives BL low.

The service restarted successfully and reached the main menu; GPIO24 was high
after the splash. Renderer ordering was verified with a fake driver, including
leaving BL off if the image write fails. The operator subsequently reported a
2–3 second initial flash, then BL turns off before the booting screen appears.
The firmware setting cannot control the instant before firmware reads config.

Renderer, boot config and prior drop-ins backup:
`/var/backups/kronoskvm/lcd-backlight-20261004.s0Ipkg`.
