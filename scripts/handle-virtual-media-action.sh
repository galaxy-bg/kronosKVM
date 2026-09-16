#!/usr/bin/env bash
set -Eeuo pipefail

state_dir=/var/lib/kronoskvm/state
request="${state_dir}/virtual-media-action"
status_file="${state_dir}/virtual-media-status"
storage_root=/mnt/kronoskvm-storage
lun=/sys/kernel/config/usb_gadget/kronoskvm/functions/mass_storage.usb0/lun.0

[[ -f "${request}" ]] || exit 0
IFS= read -r action <"${request}" || true
filename="$(sed -n '2p' "${request}")"
rm -f -- "${request}"

write_status() {
    local state="$1" media_name="${2:-}" media_type="${3:-}" message="${4:-}"
    local temporary="${status_file}.tmp"
    printf 'status=%s\nfilename=%s\nmedia_type=%s\nmessage=%s\n' \
        "${state}" "${media_name}" "${media_type}" "${message}" >"${temporary}"
    chown 10001:20 "${temporary}"
    chmod 0640 "${temporary}"
    mv -f -- "${temporary}" "${status_file}"
}

trap 'write_status error "${filename:-}" "" "Virtual media operation failed; check the host service log"' ERR

if [[ ! -d "${lun}" ]]; then
    write_status unavailable "" "" "USB virtual-media gadget is not configured"
    exit 1
fi

case "${action}" in
  attach)
    if [[ -z "${filename}" || "${filename}" == .* || "${filename}" == */* || "${filename}" == *\\* ]]; then
        write_status error "" "" "Invalid media filename"
        exit 1
    fi
    candidate="${storage_root}/${filename}"
    if [[ ! -f "${candidate}" || -L "${candidate}" ]]; then
        write_status error "${filename}" "" "Staged media file was not found"
        exit 1
    fi
    resolved="$(realpath -- "${candidate}")"
    if [[ "${resolved}" != "${storage_root}/"* ]]; then
        write_status error "${filename}" "" "Media path is outside staging storage"
        exit 1
    fi
    script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
    if ! media_type="$(python3 "${script_dir}/detect-virtual-media-type.py" "${resolved}" 2>&1)"; then
        write_status error "${filename}" "" "${media_type}"
        exit 1
    fi
    cdrom=0
    [[ "${media_type}" != cdrom ]] || cdrom=1
    printf '\n' >"${lun}/file"
    printf '%s' "${cdrom}" >"${lun}/cdrom"
    printf '1' >"${lun}/ro"
    printf '%s' "${resolved}" >"${lun}/file"
    write_status attached "${filename}" "${media_type}" "Read-only virtual media is active"
    logger --tag kronoskvm-media "Attached read-only virtual media: ${filename} (${media_type})"
    ;;
  eject)
    printf '\n' >"${lun}/file"
    write_status ejected "" "" "Virtual media ejected"
    logger --tag kronoskvm-media "Ejected virtual media"
    ;;
  *)
    write_status error "" "" "Invalid virtual media action"
    exit 1
    ;;
esac
