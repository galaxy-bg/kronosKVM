# Base Operating-System Preparation

## Current baseline

The prototype runs Debian GNU/Linux 11 Bullseye with Raspberry Pi kernel
`6.1.21-v8+`. This installation is suitable for hardware discovery, but it is
not the intended production baseline.

Do not perform an in-place major-version upgrade. Before application deployment,
back up any required device-specific information and provision a current,
supported Raspberry Pi OS Lite 64-bit image. Re-run inventory after imaging.

## Milestone 2 safe scope

`scripts/bootstrap.sh` performs only these idempotent actions:

- creates the locked `kronoskvm` service account and group;
- creates `/etc/kronoskvm`, `/var/lib/kronoskvm`,
  `/var/lib/kronoskvm/images`, `/var/log/kronoskvm`, `/run/kronoskvm` and
  `/opt/kronoskvm`;
- configures tmpfiles for runtime state;
- limits persistent journal use to 256 MiB and 14 days;
- verifies Europe/Istanbul timezone and NTP synchronization.

It does not install packages, upgrade the OS, change networking or firewall
rules, install services, edit boot files or reboot.

Preview:

```bash
sudo ./scripts/bootstrap.sh --dry-run
```

Apply:

```bash
sudo ./scripts/bootstrap.sh
./scripts/verify-base-os.sh
```

## Deferred work

- Select and image a supported Raspberry Pi OS Lite 64-bit baseline.
- Map chassis ETH0/ETH1 before firewall rules reference interfaces.
- Preserve SSH first, then apply explicit default-deny inbound rules.
- Review the existing Bluetooth failure after the OS baseline is replaced.
