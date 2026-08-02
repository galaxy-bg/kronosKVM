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
