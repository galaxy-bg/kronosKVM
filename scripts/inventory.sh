#!/usr/bin/env bash
set -Eeuo pipefail

log_warn() { printf '[WARN] %s\n' "$*" >&2; }
have_command() { command -v "$1" >/dev/null 2>&1; }
run_optional() {
    local title="$1"
    shift
    printf '\n===== %s =====\n' "${title}"
    if have_command "$1"; then
        "$@" 2>&1 || log_warn "Command failed or returned partial data: $*"
    else
        log_warn "Command unavailable: $1"
    fi
}

usage() {
    cat <<'EOF'
Usage: inventory.sh [--help]

Print a read-only hardware and operating-system inventory to stdout.
No passwords, private keys, shell history, environment variables or Wi-Fi
pre-shared keys are collected.
EOF
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    usage
    exit 0
fi
if (( $# > 0 )); then
    usage >&2
    exit 2
fi

printf 'KronosKVM read-only inventory\n'
printf 'timestamp_utc=%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
printf 'hostname=%s\n' "$(hostname 2>/dev/null || printf unknown)"

run_optional "hostnamectl" hostnamectl
run_optional "uname" uname -a
run_optional "os-release" sed -n '1,120p' /etc/os-release
run_optional "device-tree-model" tr -d '\0' </proc/device-tree/model
run_optional "cpuinfo" sed -n '1,240p' /proc/cpuinfo
run_optional "lscpu" lscpu
run_optional "memory" free -h
run_optional "block-devices" lsblk -o NAME,MODEL,SERIAL,SIZE,TYPE,FSTYPE,MOUNTPOINT
run_optional "mounts" findmnt
run_optional "filesystems" df -hT
run_optional "network-links" ip -br link
run_optional "network-addresses" ip -br address
run_optional "routes" ip route
run_optional "rules" ip rule
run_optional "bridge-links" bridge link
run_optional "bridge-vlans" bridge vlan show
run_optional "listening-sockets" ss -lntup
run_optional "usb-devices" lsusb
run_optional "usb-topology" lsusb -t
run_optional "pci-devices" lspci
run_optional "rfkill" rfkill list
run_optional "wifi-interfaces" iw dev
run_optional "wifi-capabilities" iw phy
run_optional "failed-services" systemctl --failed --no-pager
run_optional "time" timedatectl
run_optional "journal-warnings" journalctl -p warning..alert -b --no-pager
run_optional "kernel-warnings" dmesg --level=err,warn
run_optional "video-devices" bash -c 'ls -l /dev/video* /dev/media* 2>/dev/null || true'
run_optional "serial-devices" bash -c 'ls -l /dev/ttyUSB* /dev/ttyACM* 2>/dev/null || true'
run_optional "rtc-devices" bash -c 'ls -l /dev/rtc* 2>/dev/null || true'
run_optional "i2c-devices" bash -c 'ls -l /dev/i2c* 2>/dev/null || true'
run_optional "gpio-devices" bash -c 'ls -l /dev/gpiochip* 2>/dev/null || true'
run_optional "usb-device-controllers" bash -c 'ls -la /sys/class/udc 2>/dev/null || true'
run_optional "usb-gadgets" bash -c \
    'find /sys/kernel/config/usb_gadget -maxdepth 3 -print 2>/dev/null || true'
run_optional "v4l2-devices" v4l2-ctl --list-devices
run_optional "throttling" vcgencmd get_throttled
run_optional "temperature" vcgencmd measure_temp
run_optional "arm-memory" vcgencmd get_mem arm
run_optional "gpu-memory" vcgencmd get_mem gpu
run_optional "camera" vcgencmd get_camera

printf '\n===== ethernet-drivers =====\n'
for interface_path in /sys/class/net/*; do
    [[ -e "${interface_path}" ]] || continue
    interface="${interface_path##*/}"
    printf '\n--- %s ---\n' "${interface}"
    readlink -f "${interface_path}/device" 2>/dev/null || true
    if have_command ethtool; then
        ethtool -i "${interface}" 2>&1 || true
    fi
done

for boot_file in \
    /boot/firmware/config.txt /boot/config.txt \
    /boot/firmware/cmdline.txt /boot/cmdline.txt; do
    printf '\n===== boot-file:%s =====\n' "${boot_file}"
    if [[ -r "${boot_file}" ]]; then
        sed -E '/^[[:space:]]*(#|$)/d' "${boot_file}" 2>/dev/null || true
    else
        log_warn "Unreadable or absent: ${boot_file}"
    fi
done
