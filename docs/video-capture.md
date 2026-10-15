# Video Capture

The active capture path is:

```text
Target HDMI → Geekworm X630 / TC358743 → CSI-2 → /dev/video0
```

The TC358743 bridge loses EDID across a power cycle. The host systemd service
runs `scripts/configure-capture.sh` before starting the application containers;
the script installs an HDMI EDID and applies detected DV timings when a source
is present.

The API reports live signal and resolution at `GET /api/v1/video/status` and
serves the browser stream from `/api/v1/video/stream.mjpg`.

Verified input includes 1024×768 at 60 Hz. `Cable detected` without TMDS, PLL
lock or stable sync means the HDMI cable is present but the target is not
emitting video; it is not an application-stream failure.

## Complete-frame browser display — 2026-10-08

The operator reported transient white areas during target-screen changes.
Twelve complete JPEG samples from the current PXE screen decoded cleanly, with
dark bottom rows; these samples did not reproduce the earlier BIOS transition.
Partial browser MJPEG painting was treated as a possible cause, not a proven
hardware diagnosis.

The frontend now fetches the authenticated MJPEG stream, assembles bounded
complete JPEG frames and decodes each off-screen before replacing the visible
image with a Blob URL. The last decoded frame remains during reconnect and
pause; a generation guard prevents late frames from changing a stopped window.
Closing the KVM window aborts the fetch and releases its Blob URL. Capture
settings and the backend streaming API are unchanged.

Deployed to both appliances; the
[first-box update record](first-appliance-update-20261008.md) records its
pending real-target image check. On the second appliance (`192.168.1.107`),
live Chrome verified
1024×768 decoded Blob display, HID connection, a stable paused image and resumed
frame updates, without page errors. Parser tests cover all multipart split
positions, one-byte chunks, multiple frames, buffer limits, decode-before-paint
and stop races. The original BIOS-transition artifact still requires operator
retesting, particularly in the operator's browser.

Frontend backup:
`/var/backups/kronoskvm/pre-complete-frames-20261008.4461z1/frontend.tar.gz`.
Previous web image: `kronoskvm-web:pre-complete-frames-20261008`.
Updated web image: `kronoskvm-web:complete-frames-20261008`, also tagged `:dev`.
Only the web container was rebuilt/recreated. Refresh the browser and reopen
KVM to load the new display code.
