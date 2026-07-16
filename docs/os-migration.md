# Operating-System Update and Migration

## Current-release updates

Use `scripts/update-current-os.sh` to update packages, stable kernel and
firmware within the configured release. It creates a local root-only backup of
APT and boot configuration before applying `apt-get full-upgrade`.

Preview:

```bash
sudo ./scripts/update-current-os.sh --dry-run
```

Apply:

```bash
sudo ./scripts/update-current-os.sh
sudo reboot
```

This script never edits APT release codenames.

## Major release migration

The prototype currently runs Debian/Raspberry Pi OS Bullseye. Raspberry Pi
officially recommends a clean image instead of an in-place major upgrade. The
production migration target is the current Raspberry Pi OS Lite 64-bit release.

Migration requires physical or out-of-band access:

1. Preserve inventory and required configuration.
2. Prepare new boot media with Raspberry Pi Imager.
3. Configure hostname, `kronosdx` user, SSH and management Wi-Fi.
4. Boot the new media and verify SSH host keys intentionally.
5. Re-run `scripts/remote-inventory.sh`.
6. Apply `scripts/bootstrap.sh`.
7. Revalidate Ethernet, USB, UDC, RTC, display and capture hardware.

Do not change Bullseye APT sources to Bookworm or Trixie for an unattended
remote upgrade.
