#!/usr/bin/env bash
set -Eeuo pipefail

# Configure the TC358743 HDMI-to-CSI bridge. The bridge loses its EDID on every
# power cycle, so the source will not reliably emit video until this runs.

subdev=""
for _ in {1..20}; do
  for name_file in /sys/class/video4linux/v4l-subdev*/name; do
    [[ -r "$name_file" ]] || continue
    if grep -q '^tc358743 ' "$name_file"; then
      subdev="/dev/$(basename "$(dirname "$name_file")")"
      break 2
    fi
  done
  sleep 0.5
done

if [[ -z "$subdev" ]]; then
  echo "WARNING: TC358743 capture bridge was not found; skipping HDMI setup" >&2
  exit 0
fi

# The generic HDMI EDID advertises 1080p60, which exceeds this two-lane
# X630 configuration. Prefer 720p60 while retaining legacy PC and 1080p30 modes.
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
edid_file="${project_dir}/config/edid/infrabox-compat.hex"
if [[ ! -s "$edid_file" ]]; then
  echo "ERROR: Capture compatibility EDID is missing: $edid_file" >&2
  exit 1
fi
v4l2-ctl -d "$subdev" --set-edid "pad=0,file=$edid_file"

# Give the HDMI source time to react to hotplug. Lack of signal must not block
# the rest of KronosKVM from starting; the API configures timings on capture.
for _ in {1..10}; do
  if v4l2-ctl -d "$subdev" --query-dv-timings >/dev/null 2>&1; then
    v4l2-ctl -d /dev/video0 --set-dv-bt-timings=query >/dev/null 2>&1 || true
    break
  fi
  sleep 0.5
done

echo "TC358743 HDMI capture initialized on $subdev"
