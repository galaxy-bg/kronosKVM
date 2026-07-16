# Implementation Log

## 2026-07-16

- Created the public GitHub repository and initial prototype.
- Adopted the detailed KronosKVM engineering specification.
- Began Milestone 0 structure and read-only Milestone 1 tooling.
- Configured local SSH public-key access without storing a password.
- Verified the target host as `kdx-ikvm` and completed read-only inventory.
- Confirmed Debian 11, CM4 Rev 1.1, 4 GB class memory and Wi-Fi management.
- Found no registered UDC, RTC, serial or HDMI capture hardware.
- No target package, boot, network, firewall, gadget or service changes performed.

## Milestone 2

- Reviewed OS, time, journal, firewall, user and filesystem state.
- Confirmed passwordless sudo, persistent journal, synchronized NTP and
  Europe/Istanbul timezone.
- Deferred package installation and firewall changes because Bullseye is not
  the production baseline and chassis Ethernet mapping is incomplete.
- Created the locked `kronoskvm` service account and protected application,
  configuration, data, image, log and runtime directories.
- Added tmpfiles runtime creation and bounded persistent journal retention.
- Verified SSH remained reachable; no reboot was required.

## OS maintenance

- Adopted current-release `apt full-upgrade` with pre-update configuration
  backup.
- Kept APT release codenames unchanged.
- Documented clean Raspberry Pi OS Lite 64-bit imaging for major migration.
- Reviewed the full-upgrade simulation and disabled automatic package removal.
- Applied the Bullseye current-release update on 2026-07-16:
  `libxfont2`, `p7zip`, `p7zip-full` and `wireless-regdb`.
- Removed no packages and changed no APT release codenames.
- Stored a root-only pre-update backup under `/var/backups/kronoskvm/`.
- Rebooted successfully; SSH and `192.168.31.145` Wi-Fi management returned.
- Verified no pending package upgrades, no throttling and synchronized NTP.
- The existing `bthelper@hci0.service` failure remains for later OS migration
  review.

## Milestone 3

- Implemented typed read-only FastAPI endpoints for health, capabilities,
  system, network, storage, services and optional hardware.
- Added request IDs, structured JSON application logs and safe error responses.
- Added Python 3.9 compatibility for the current Bullseye device.
- Installed `kronoskvm-api.service` as the locked `kronoskvm` user.
- Bound the service exclusively to `127.0.0.1:8000`.
- Verified all API endpoints on the CM4 using real system data.
- Confirmed the service is enabled, active and stable with zero restarts after
  the Python 3.9 compatibility fix.
- Updated deployment to restart the API explicitly after application upgrades,
  ensuring new code replaces the running process.

## Milestone 4

- Added USB serial discovery for `/dev/ttyUSB*` and `/dev/ttyACM*`.
- Added VID, PID, serial number, kernel driver and stable by-id/by-path metadata.
- Added 9600, 19200, 38400 and 115200 8N1 profiles.
- Added exclusive in-memory device locks with token-based release.
- Installed PySerial 3.5 and granted the service supplementary `dialout` access.
- Verified the no-adapter state on the CM4: empty inventory and
  `not_detected` capability.
- Verified unknown devices cannot be locked.
- Confirmed TCP ports 2001 and 2002 remain closed.
- No serial device was opened and no serial data was read or written.
