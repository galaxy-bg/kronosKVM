#!/usr/bin/env bash
# Resolve the wlan0 AP by UUID; profile names differ between appliances.

active_management_ap_uuid() {
    local uuid mode
    uuid="$(nmcli -g GENERAL.CON-UUID device show wlan0 2>/dev/null || true)"
    [[ -n "${uuid}" && "${uuid}" != -- ]] || return 1
    mode="$(nmcli -g 802-11-wireless.mode connection show uuid "${uuid}" 2>/dev/null || true)"
    [[ "${mode}" == ap ]] || return 1
    printf '%s' "${uuid}"
}

management_ap_uuid() {
    local uuid interface mode selected=""
    if uuid="$(active_management_ap_uuid)"; then
        printf '%s' "${uuid}"
        return 0
    fi
    while IFS= read -r uuid; do
        [[ -n "${uuid}" ]] || continue
        interface="$(nmcli -g connection.interface-name connection show uuid "${uuid}" 2>/dev/null || true)"
        [[ "${interface}" == wlan0 ]] || continue
        mode="$(nmcli -g 802-11-wireless.mode connection show uuid "${uuid}" 2>/dev/null || true)"
        [[ "${mode}" == ap ]] || continue
        # An ambiguous inactive configuration must not activate an arbitrary AP.
        [[ -z "${selected}" ]] || return 1
        selected="${uuid}"
    done < <(nmcli -g UUID connection show 2>/dev/null || true)
    [[ -n "${selected}" ]] || return 1
    printf '%s' "${selected}"
}
