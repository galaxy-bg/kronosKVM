#!/usr/bin/env bash
set -Eeuo pipefail

state_dir=/var/lib/kronoskvm/state
request="${state_dir}/service-action"
[[ -f "${request}" ]] || exit 0

value() { sed -n "s/^$1=//p" "${request}" | head -1; }
service="$(value service)"
action="$(value action)"
task_id="$(value task_id)"
rm -f -- "${request}"

[[ "${task_id}" =~ ^[0-9a-f-]{36}$ ]] || exit 1

unit_for() {
    case "$1" in
        containers) printf '%s' kronoskvm-containers.service ;;
        docker) printf '%s' docker.service ;;
        dnsmasq) printf '%s' dnsmasq.service ;;
        networkmanager) printf '%s' NetworkManager.service ;;
        ssh) printf '%s' ssh.service ;;
        wittypi) printf '%s' wittypi.service ;;
        *) return 1 ;;
    esac
}

write_status() {
    local temporary="${state_dir}/.service-status.tmp" id unit state detail first=true
    printf '{"updated_at":"%s","services":{' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >"${temporary}"
    for id in containers docker dnsmasq networkmanager ssh wittypi; do
        unit="$(unit_for "${id}")"
        state="$(systemctl is-active "${unit}" 2>/dev/null || true)"
        [[ -n "${state}" ]] || state=unknown
        if ! systemctl cat "${unit}" >/dev/null 2>&1; then state=not_installed; fi
        detail="${unit}"
        "${first}" || printf ',' >>"${temporary}"
        first=false
        printf '"%s":{"state":"%s","detail":"%s"}' "${id}" "${state}" "${detail}" >>"${temporary}"
    done
    state=inactive
    [[ "$(nmcli -g GENERAL.CONNECTION device show wlan0 2>/dev/null || true)" == KronosDX-iKVM ]] && state=active
    printf ',"management_ap":{"state":"%s","detail":"NetworkManager · KronosDX-iKVM"}' "${state}" >>"${temporary}"
    printf ',"tftp":{"state":"not_configured","detail":"Recovery Network required"}' >>"${temporary}"
    printf ',"recovery_http":{"state":"not_configured","detail":"Recovery Network required"}}}\n' >>"${temporary}"
    chown 10001:20 "${temporary}"
    chmod 0640 "${temporary}"
    mv -f -- "${temporary}" "${state_dir}/service-status.json"

    for id in containers docker dnsmasq networkmanager ssh wittypi; do
        unit="$(unit_for "${id}")"
        temporary="${state_dir}/.service-log-${id}.tmp"
        journalctl -u "${unit}" -n 100 --no-pager -o short-iso >"${temporary}" 2>/dev/null || true
        chown 10001:20 "${temporary}"
        chmod 0640 "${temporary}"
        mv -f -- "${temporary}" "${state_dir}/service-log-${id}.log"
    done
    journalctl -u NetworkManager.service -n 100 --no-pager -o short-iso >"${state_dir}/.service-log-management_ap.tmp" 2>/dev/null || true
    chown 10001:20 "${state_dir}/.service-log-management_ap.tmp"
    chmod 0640 "${state_dir}/.service-log-management_ap.tmp"
    mv -f -- "${state_dir}/.service-log-management_ap.tmp" "${state_dir}/service-log-management_ap.log"
}

successful=true
error=""
if [[ "${action}" == restart ]]; then
    if [[ "${service}" == management_ap ]]; then
        if ! nmcli connection up KronosDX-iKVM; then
            successful=false
            error="Management AP restart failed"
        fi
    elif unit="$(unit_for "${service}")"; then
        if ! systemctl restart "${unit}"; then
            successful=false
            error="Service restart failed"
        fi
    else
        successful=false
        error="Rejected service"
    fi
elif [[ "${action}" != refresh || "${service}" != all ]]; then
    successful=false
    error="Rejected action"
fi

write_status
result="${state_dir}/service-result-${task_id}.json"
printf '{"successful":%s,"error":"%s","service":"%s","action":"%s"}\n' \
    "${successful}" "${error}" "${service}" "${action}" >"${result}"
chown 10001:20 "${result}"
chmod 0640 "${result}"
logger --tag kdx-infrabox-services "${action} ${service}: ${successful}"
