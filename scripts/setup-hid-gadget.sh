#!/usr/bin/env bash
set -Eeuo pipefail

gadget=/sys/kernel/config/usb_gadget/kronoskvm
udc=fe980000.usb

modprobe libcomposite
mkdir -p "${gadget}"

if [[ -d "${gadget}/functions/hid.keyboard" && -d "${gadget}/functions/hid.mouse" && -d "${gadget}/functions/hid.mouse_relative" ]]; then
    if [[ -z "$(cat "${gadget}/UDC" 2>/dev/null || true)" ]]; then
        printf '%s' "${udc}" >"${gadget}/UDC"
    fi
    chmod 0660 /dev/hidg0 /dev/hidg1 /dev/hidg2
    chgrp dialout /dev/hidg0 /dev/hidg1 /dev/hidg2
    exit 0
fi

# Rebuild older two-interface gadgets so the target enumerates the BIOS-compatible
# boot mouse as a third HID interface.
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
printf '0' >"${gadget}/functions/hid.mouse/subclass"
printf '6' >"${gadget}/functions/hid.mouse/report_length"
printf '\x05\x01\x09\x02\xa1\x01\x09\x01\xa1\x00\x05\x09\x19\x01\x29\x03\x15\x00\x25\x01\x95\x03\x75\x01\x81\x02\x95\x01\x75\x05\x81\x01\x05\x01\x09\x30\x09\x31\x16\x00\x00\x26\xff\x7f\x75\x10\x95\x02\x81\x02\x09\x38\x15\x81\x25\x7f\x75\x08\x95\x01\x81\x06\xc0\xc0' >"${gadget}/functions/hid.mouse/report_desc"

mkdir -p "${gadget}/functions/hid.mouse_relative"
printf '2' >"${gadget}/functions/hid.mouse_relative/protocol"
printf '1' >"${gadget}/functions/hid.mouse_relative/subclass"
printf '4' >"${gadget}/functions/hid.mouse_relative/report_length"
printf '\x05\x01\x09\x02\xa1\x01\x09\x01\xa1\x00\x05\x09\x19\x01\x29\x03\x15\x00\x25\x01\x95\x03\x75\x01\x81\x02\x95\x01\x75\x05\x81\x01\x05\x01\x09\x30\x09\x31\x09\x38\x15\x81\x25\x7f\x75\x08\x95\x03\x81\x06\xc0\xc0' >"${gadget}/functions/hid.mouse_relative/report_desc"

ln -sfn "${gadget}/functions/hid.keyboard" "${gadget}/configs/c.1/hid.keyboard"
ln -sfn "${gadget}/functions/hid.mouse" "${gadget}/configs/c.1/hid.mouse"
ln -sfn "${gadget}/functions/hid.mouse_relative" "${gadget}/configs/c.1/hid.mouse_relative"

printf '%s' "${udc}" >"${gadget}/UDC"
chmod 0660 /dev/hidg0 /dev/hidg1 /dev/hidg2
chgrp dialout /dev/hidg0 /dev/hidg1 /dev/hidg2
