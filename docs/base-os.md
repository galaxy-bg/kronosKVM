# Base Operating-System Preparation

## Current baseline

The active prototype runs Debian GNU/Linux 13 on a Raspberry Pi 4 Model B with
the Raspberry Pi `6.18.34+rpt-rpi-v8` aarch64 kernel. The root filesystem is on
a 64 GB microSD card.

The installation provides:

- Docker and systemd-managed KronosKVM containers
- native Ethernet plus the permanent Wi-Fi management AP
- DWC2 peripheral mode on USB-C
- TC358743/X630 device-tree overlay and capture initialization
- persistent journald and structured application logs

Do not perform an in-place major-version upgrade on an appliance. Re-image a
separate card, validate hardware inventory and retain the prior card as the
rollback path.

## Preparation

```bash
sudo ./scripts/bootstrap.sh --dry-run
sudo ./scripts/bootstrap.sh
sudo ./scripts/install-dependencies.sh
sudo ./scripts/install-containers.sh
./scripts/verify-base-os.sh
```

`bootstrap.sh` creates the service account and required filesystem layout. It
does not silently reconfigure networking, boot overlays or reboot the host.

## Required boot overlays

The active appliance requires both overlays under the global `[all]` section:

```ini
dtoverlay=dwc2,dr_mode=peripheral
dtoverlay=tc358743
```

After imaging a new card, verify `/sys/class/udc/fe980000.usb`, `/dev/video0`,
Ethernet, AP access and both physical console paths before deployment.
