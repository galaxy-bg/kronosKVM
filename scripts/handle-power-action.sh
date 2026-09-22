#!/usr/bin/env bash
set -Eeuo pipefail

request=/var/lib/kronoskvm/state/power-action
[[ -f "${request}" ]] || exit 0

action="$(tr -d '[:space:]' <"${request}")"
rm -f -- "${request}"

case "${action}" in
  reboot)
    logger --tag kronoskvm-power "Approved appliance reboot requested from management UI"
    sleep 3
    systemctl reboot
    ;;
  poweroff)
    logger --tag kronoskvm-power "Approved appliance power off requested from management UI"
    sleep 3
    systemctl poweroff
    ;;
  *)
    logger --tag kronoskvm-power --priority user.warning "Rejected invalid power action: ${action}"
    exit 1
    ;;
esac
