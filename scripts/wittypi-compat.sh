#!/usr/bin/env bash
# Loaded after pinned manufacturer utilities.sh. Service and vendor commands use UTC.
export TZ=UTC

is_mc_connected() {
    local identity
    identity=$(i2cget -y 1 0x08 0 b 2>/dev/null) || { echo 0; return; }
    [[ "$identity" == 0x26 ]] && echo 1 || echo 0
}

one_wire_confliction() {
    grep -Eq '^[[:space:]]*dtoverlay=w1-gpio(-pullup)?([[:space:]]*$|,.*gpiopin=4([,[:space:]]|$))' /boot/firmware/config.txt
}

rtc_to_system() {
    if [[ $(timedatectl show -p NTPSynchronized --value) == yes ]]; then
        log 'System clock is NTP synchronized; retaining system time and NTP.'
        return
    fi
    local stamp
    stamp=$(get_rtc_timestamp) || return 1
    [[ "$stamp" =~ ^[0-9]+$ && "$stamp" -ge 1704067200 ]] || return 1
    date -u -s "@$stamp" >/dev/null || return 1
    TIME_UNKNOWN=0
    log 'System initialized from Witty Pi RTC (UTC); NTP remains enabled.'
}
