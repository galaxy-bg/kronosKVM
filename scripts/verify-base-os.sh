#!/usr/bin/env bash
set -Eeuo pipefail

failures=0

check() {
    local description="$1"
    shift
    if "$@"; then
        printf '[PASS] %s\n' "${description}"
    else
        printf '[FAIL] %s\n' "${description}" >&2
        failures=$((failures + 1))
    fi
}

root_test() {
    if (( EUID == 0 )); then
        test "$@"
    else
        sudo -n test "$@"
    fi
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    printf 'Usage: verify-base-os.sh\nVerify the Milestone 2 base OS preparation.\n'
    exit 0
fi
if (( $# > 0 )); then
    exit 2
fi

check "kronoskvm group exists" getent group kronoskvm
check "kronoskvm user exists" getent passwd kronoskvm
check "service account is locked" test "$(getent passwd kronoskvm | cut -d: -f7)" = /usr/sbin/nologin
check "configuration directory exists" root_test -d /etc/kronoskvm
check "data directory exists" root_test -d /var/lib/kronoskvm
check "image directory exists" root_test -d /var/lib/kronoskvm/images
check "runtime directory exists" root_test -d /run/kronoskvm
check "log directory exists" root_test -d /var/log/kronoskvm
check "application directory exists" root_test -d /opt/kronoskvm
check "persistent journal exists" test -d /var/log/journal
check "timezone is Europe/Istanbul" test \
    "$(timedatectl show -p Timezone --value)" = Europe/Istanbul
check "NTP is synchronized" test \
    "$(timedatectl show -p NTPSynchronized --value)" = yes

exit "${failures}"
