#!/usr/bin/env bash
set -Eeuo pipefail

state_dir=/var/lib/kronoskvm/state
request="${state_dir}/network-action"
[[ -f "${request}" ]] || exit 0

value() { sed -n "s/^$1=//p" "${request}" | head -1; }
interface="$(value interface)"
mode="$(value mode)"
address="$(value address)"
gateway="$(value gateway)"
dns="$(value dns)"
rm -f -- "${request}"

if [[ ! "${interface}" =~ ^[A-Za-z0-9_.:-]{1,15}$ \
    || "${interface}" == "lo" || "${interface}" == "wlan0" \
    || ! -d "/sys/class/net/${interface}" || -d "/sys/class/net/${interface}/wireless" ]]; then
    logger --tag kronoskvm-network --priority user.warning "Rejected protected or invalid interface"
    exit 1
fi
if [[ "${mode}" != "dhcp" && "${mode}" != "static" ]]; then
    logger --tag kronoskvm-network --priority user.warning "Rejected invalid mode for ${interface}"
    exit 1
fi

profile="$(nmcli -g GENERAL.CONNECTION device show "${interface}" 2>/dev/null || true)"
if [[ -z "${profile}" || "${profile}" == "--" ]]; then
    profile="KronosKVM ${interface}"
    nmcli connection add type ethernet ifname "${interface}" con-name "${profile}"
fi

status_file="${state_dir}/network-config-${interface}"
write_status() {
    local result="$1" message="$2" temporary="${status_file}.tmp"
    printf 'mode=%s\naddress=%s\ngateway=%s\ndns=%s\nstatus=%s\nmessage=%s\n' \
        "${mode}" "${address}" "${gateway}" "${dns}" "${result}" "${message}" >"${temporary}"
    chown 10001:20 "${temporary}"
    chmod 0640 "${temporary}"
    mv -f -- "${temporary}" "${status_file}"
}

write_status applying "Applying network configuration"
if [[ "${mode}" == "dhcp" ]]; then
    nmcli connection modify "${profile}" \
        ipv4.method auto ipv4.addresses "" ipv4.gateway "" ipv4.dns "" \
        ipv4.ignore-auto-dns no
else
    [[ "${address}" =~ ^[0-9.]+/[0-9]{1,2}$ ]] || exit 1
    [[ -z "${gateway}" || "${gateway}" =~ ^[0-9.]+$ ]] || exit 1
    [[ -z "${dns}" || "${dns}" =~ ^[0-9.,]+$ ]] || exit 1
    nmcli connection modify "${profile}" \
        ipv4.method manual ipv4.addresses "${address}" ipv4.gateway "${gateway}" \
        ipv4.dns "${dns}" ipv4.ignore-auto-dns yes
fi

if nmcli connection up "${profile}" ifname "${interface}"; then
    write_status applied "Network configuration applied"
    logger --tag kronoskvm-network "Applied ${mode} configuration to ${interface}"
else
    write_status failed "NetworkManager could not activate the configuration"
    exit 1
fi
