#!/usr/bin/env bash
set -Eeuo pipefail

gadget=/sys/kernel/config/usb_gadget/kronoskvm

modprobe libcomposite

udc_path="$(find /sys/class/udc -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null || true)"
if [[ -z "${udc_path}" ]]; then
    printf '[WARN] No USB device controller is available; skipping HID gadget setup.\n'
    exit 0
fi
udc="$(basename "${udc_path}")"

mkdir -p "${gadget}"

if [[ -d "${gadget}/functions/hid.keyboard" \
    && -d "${gadget}/functions/hid.mouse" \
    && ! -d "${gadget}/functions/hid.mouse_relative" \
    && "$(cat "${gadget}/functions/hid.mouse/report_length" 2>/dev/null || true)" == "3" ]]; then
    if [[ -z "$(cat "${gadget}/UDC" 2>/dev/null || true)" ]]; then
        printf '%s' "${udc}" >"${gadget}/UDC"
    fi
    chmod 0660 /dev/hidg0 /dev/hidg1
    chgrp dialout /dev/hidg0 /dev/hidg1
    exit 0
fi

# Keep the Pi 4 DWC2 gadget deliberately small: one keyboard and one
# BIOS-compatible boot mouse. A third periodic HID endpoint proved unstable on
# this controller and caused the complete USB transport to reset.
if [[ -d "${gadget}" ]]; then
    printf '' >"${gadget}/UDC" 2>/dev/null || true
    rm -f "${gadget}/configs/c.1/hid.keyboard" \
        "${gadget}/configs/c.1/hid.mouse" \
        "${gadget}/configs/c.1/hid.mouse_relative"
    rmdir "${gadget}/functions/hid.keyboard" \
        "${gadget}/functions/hid.mouse" \
        "${gadget}/functions/hid.mouse_relative" 2>/dev/null || true
fi

printf '0x1d6b' >"${gadget}/idVendor"
printf '0x0104' >"${gadget}/idProduct"
printf '0x0100' >"${gadget}/bcdDevice"
printf '0x0200' >"${gadget}/bcdUSB"

mkdir -p "${gadget}/strings/0x409"
printf 'KRONOSKVM001' >"${gadget}/strings/0x409/serialnumber"
printf 'KronosDX' >"${gadget}/strings/0x409/manufacturer"
printf 'KronosKVM Keyboard and Mouse' >"${gadget}/strings/0x409/product"

mkdir -p "${gadget}/configs/c.1/strings/0x409"
printf 'HID control' >"${gadget}/configs/c.1/strings/0x409/configuration"
printf '120' >"${gadget}/configs/c.1/MaxPower"

mkdir -p "${gadget}/functions/hid.keyboard"
printf '1' >"${gadget}/functions/hid.keyboard/protocol"
printf '1' >"${gadget}/functions/hid.keyboard/subclass"
printf '8' >"${gadget}/functions/hid.keyboard/report_length"
printf '\x05\x01\x09\x06\xa1\x01\x05\x07\x19\xe0\x29\xe7\x15\x00\x25\x01\x75\x01\x95\x08\x81\x02\x95\x01\x75\x08\x81\x01\x95\x05\x75\x01\x05\x08\x19\x01\x29\x05\x91\x02\x95\x01\x75\x03\x91\x01\x95\x06\x75\x08\x15\x00\x25\x65\x05\x07\x19\x00\x29\x65\x81\x00\xc0' >"${gadget}/functions/hid.keyboard/report_desc"

mkdir -p "${gadget}/functions/hid.mouse"
printf '2' >"${gadget}/functions/hid.mouse/protocol"
printf '1' >"${gadget}/functions/hid.mouse/subclass"
printf '3' >"${gadget}/functions/hid.mouse/report_length"
printf '\x05\x01\x09\x02\xa1\x01\x09\x01\xa1\x00\x05\x09\x19\x01\x29\x03\x15\x00\x25\x01\x95\x03\x75\x01\x81\x02\x95\x01\x75\x05\x81\x01\x05\x01\x09\x30\x09\x31\x15\x81\x25\x7f\x75\x08\x95\x02\x81\x06\xc0\xc0' >"${gadget}/functions/hid.mouse/report_desc"

ln -sfn "${gadget}/functions/hid.keyboard" "${gadget}/configs/c.1/hid.keyboard"
ln -sfn "${gadget}/functions/hid.mouse" "${gadget}/configs/c.1/hid.mouse"

printf '%s' "${udc}" >"${gadget}/UDC"
chmod 0660 /dev/hidg0 /dev/hidg1
chgrp dialout /dev/hidg0 /dev/hidg1
