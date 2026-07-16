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
