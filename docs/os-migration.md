# Operating-System Maintenance

## Active release

The current prototype runs Debian GNU/Linux 13 (64-bit) on the active appliance
hardware. Capture, serial-console and USB gadget functions must be revalidated
after kernel or firmware changes.

## Current-release updates

Use `scripts/update-current-os.sh` to update packages, the stable kernel and
firmware within the configured release. It creates a local root-only backup of
APT and boot configuration before applying `apt-get full-upgrade`. It does not
run `autoremove` or change the configured Debian release.

Preview:

```bash
sudo ./scripts/update-current-os.sh --dry-run
```

Apply during a maintenance window:

```bash
sudo ./scripts/update-current-os.sh
sudo reboot
```

After reboot, verify Ethernet and AP access, X630 capture, both USB consoles and
the two-interface USB-C HID gadget. When the target supplies USB VBUS, also
confirm that the final power board prevents backfeed and unsafe power sequencing.

## Major release migration

Use a clean 64-bit image for a major Debian/Raspberry Pi OS release transition.
Preserve the application configuration and inventory, provision SSH and the
management AP, run `scripts/bootstrap.sh`, deploy the containers, then repeat
the complete hardware validation. Do not perform an unattended in-place release
upgrade on the appliance.
