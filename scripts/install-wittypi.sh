#!/usr/bin/env bash
# Install verified standard Witty Pi 4 support. No reboot or firmware flashing.
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run as root'; exit 1; }
cd /opt/kronoskvm
[[ $(tr -d '\0' </proc/device-tree/model) == 'Raspberry Pi 4'* ]] || { echo 'Pi 4 required'; exit 1; }
command -v i2cget >/dev/null
command -v dtoverlay >/dev/null
# Only a single systemd owner; do not replace an unrelated existing installation.
[[ ! -e /etc/init.d/wittypi && ! -e /opt/wittypi ]] || { echo 'Review existing Witty installation first'; exit 1; }
cache_dir=$(mktemp -d /var/tmp/kdx-wittypi-install.XXXXXX)
backup_dir=$(mktemp -d /var/backups/kronoskvm/wittypi-install.XXXXXX)
chmod 700 "$cache_dir" "$backup_dir"
cp -p /boot/firmware/{config.txt,cmdline.txt} "$backup_dir/"
source_rev=d466cbc18aaea619c1f41ddb170789a661be3338
curl -fL --retry 2 "https://codeload.github.com/uugear/Witty-Pi-4/tar.gz/$source_rev" -o "$cache_dir/source.tar.gz"
echo "227f42eaf5b76ad0c629dbf1daeef8523c79c32767602c8be2aadccd15e55060  $cache_dir/source.tar.gz" | sha256sum -c -
curl -fL --retry 2 https://github.com/WiringPi/WiringPi/releases/download/v3.20/wiringpi_3.20_arm64.deb -o "$cache_dir/wiringpi.deb"
echo "85f5965d57adb895b97b3f8b04083613d00964f930cb86822459eae5a97dc804  $cache_dir/wiringpi.deb" | sha256sum -c -
[[ $(dpkg --print-architecture) == arm64 ]] || { echo 'ARM64 package required'; exit 1; }
# Activate I2C for identification; no MCU configuration writes here.
if [[ ! -e /dev/i2c-1 ]]; then dtoverlay i2c1; udevadm settle; fi
[[ $(i2cget -y 1 0x08 0 b) == 0x26 ]] || { echo 'Standard Witty Pi 4 not detected'; exit 1; }
dpkg -i "$cache_dir/wiringpi.deb"
python3 - "$cache_dir/source.tar.gz" "$source_rev" <<'PY'
import pathlib,sys,tarfile
archive,rev=sys.argv[1:]
root=pathlib.Path('/opt/wittypi')
root.mkdir(mode=0o755)
prefix=f'Witty-Pi-4-{rev}/Software/wittypi/'
with tarfile.open(archive) as tar:
    for member in tar:
        if not member.isfile() or not member.name.startswith(prefix):
            continue
        relative=pathlib.PurePosixPath(member.name[len(prefix):])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Invalid source path')
        target=root/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(tar.extractfile(member).read())
        target.chmod(0o755 if target.suffix=='.sh' else 0o644)
p=root/'utilities.sh'
s=p.read_text().replace('export LC_ALL=en_GB.UTF-8','export LC_ALL=C.UTF-8')
s=s.replace('readonly BOOT_CONFIG_FILE="/boot/config.txt"','readonly BOOT_CONFIG_FILE="/boot/firmware/config.txt"')
s+='\n# InfraBox NTP/UTC integration\nsource /opt/kronoskvm/scripts/wittypi-compat.sh\n'
p.write_text(s)
(root/'UPSTREAM_REVISION').write_text(rev+'\n')
boot=pathlib.Path('/boot/firmware/config.txt')
s=boot.read_text()
s+='\n[all]\n# KDX Witty Pi 4 I2C and OS shutdown handshake\ndtparam=i2c_arm=on\nenable_uart=1\ndtoverlay=miniuart-bt\n'
boot.write_text(s)
# Keep the UART dedicated to power-state signaling, without a serial login console.
cmd=pathlib.Path('/boot/firmware/cmdline.txt')
words=cmd.read_text().split()
cmd.write_text(' '.join(w for w in words if not w.startswith(('console=serial0,','console=ttyAMA0,')))+'\n')
PY
install -m 0644 deploy/systemd/wittypi.service /etc/systemd/system/wittypi.service
systemctl daemon-reload
python3 scripts/wittypi-host.py initialize
systemctl enable wittypi.service
if [[ $(gpio -g read 14) == 1 ]]; then
    systemctl start wittypi.service
else
    echo 'REBOOT_REQUIRED: UART boot configuration is staged; daemon remains stopped.'
fi
python3 scripts/wittypi-host.py snapshot
printf 'Witty Pi installed. Backup: %s; no reboot was performed.\n' "$backup_dir"
