#!/usr/bin/env bash
set -Eeuo pipefail

DRY_RUN=false

usage() {
    cat <<'EOF'
Usage: update-current-os.sh [--dry-run] [--help]

Update all packages within the currently configured Raspberry Pi OS/Debian
release. This script does not change APT release codenames and therefore does
not perform a major OS upgrade.

Run from a resilient SSH session. Reboot separately after reviewing results.
EOF
}

while (( $# > 0 )); do
    case "$1" in
        --dry-run) DRY_RUN=true ;;
        --help|-h) usage; exit 0 ;;
        *) printf '[ERROR] Unknown argument: %s\n' "$1" >&2; exit 2 ;;
    esac
    shift
done

if (( EUID != 0 )); then
    printf '[ERROR] Run as root.\n' >&2
    exit 1
fi

export DEBIAN_FRONTEND=noninteractive

printf '[INFO] Current release:\n'
sed -n '1,20p' /etc/os-release
printf '[INFO] Free space:\n'
df -h / /boot

apt-get update

if "${DRY_RUN}"; then
    apt-get --simulate full-upgrade
    exit 0
fi

backup_dir="/var/backups/kronoskvm/os-update-$(date -u '+%Y%m%dT%H%M%SZ')"
install -d -m 0700 "${backup_dir}"
cp -a /etc/apt/sources.list "${backup_dir}/" 2>/dev/null || true
cp -a /etc/apt/sources.list.d "${backup_dir}/" 2>/dev/null || true
cp -a /boot/config.txt /boot/cmdline.txt "${backup_dir}/" 2>/dev/null || true
dpkg-query -W >"${backup_dir}/packages-before.txt"

apt-get -y full-upgrade
apt-get clean

dpkg --audit
systemctl --failed --no-pager || true

printf '[INFO] Update completed. Autoremove was intentionally not executed.\n'
printf '[INFO] Review output, then reboot separately.\n'
