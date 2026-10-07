# First appliance update — 2026-10-07

Updated `192.168.31.185` (`kdx-infrabox`, aarch64) under `/opt/kronoskvm`
from commit `2288cb3`. Built API/web images on the appliance and installed the
pinned official ARM64 guacd image. Browser Telnet/RDP/VNC and the account-menu
changes are available. No reboot or OS update was performed.

## Recovery

- Backup: `/var/backups/kronoskvm/pre-home-update-20261007.7GTWJA`.
- `application.tar.gz` contains the previous application.
- `private-state-config.tar.gz` contains private device configuration/state;
  retain its root-only permissions.
- Previous image tags: `kronoskvm-api:pre-home-update-20261007` and
  `kronoskvm-web:pre-home-update-20261007`.
- Updated tags: `kronoskvm-api:home-update-20261007` and
  `kronoskvm-web:home-update-20261007`, also tagged `:dev`.

To roll back, restore the application archive into `/opt/kronoskvm`, tag the
previous API/web images as `:dev`, reload `kronoskvm-containers.service`, and
remove the newly added `kronoskvm-guacd` container. Restore private state only
if a separate configuration rollback is intended.

## Validation

- Isolated new-image API/auth/remote-route framing smoke test passed; nginx
  configuration validation passed.
- API, web and guacd became healthy; no failed systemd units were reported.
- API and guacd listen on loopback ports 8000 and 4822.
- Anonymous connection API requests return 401. Live Chrome verified login,
  account menu, browser connection choices and logout with no page errors.
- Administrator credential state, saved connection profiles, TLS files and
  Remote Assist configuration match the private backup byte-for-byte. Runtime
  status, history and log files continue to change during normal operation.
- Real deployed ARM64 guacd passed Telnet/VNC loopback-fixture tests for
  handshake, rendered frames and target keyboard/mouse input. The temporary
  target listeners were closed when the test finished.
- RDP plugin selection/handshake arguments passed. A real RDP target login and
  desktop-control check remain pending.

## Hardware scope

This appliance has no `infrabox-lcd.service` or `/opt/infrabox-lcd` driver
installation. LCD/backlight service configuration and BCM24 boot settings were
not applied. The separate GPIO power-button prototype was copied as source
only; no power-button service was installed/enabled and no Witty firmware was
flashed. See [power-button status](power-button.md).
