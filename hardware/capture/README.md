# Capture

Active prototype: Geekworm X630/TC358743 on CSI-2, exposed as `/dev/video0`.
EDID and DV timings are initialized by `scripts/configure-capture.sh` at boot.

The two-lane Raspberry Pi 4 configuration uses
`config/edid/infrabox-compat.hex`, rather than the generic v4l2 HDMI EDID.
The generic profile advertises 1080p60 and can cause the driver error
`Device has requested 3 data lanes, which is >2 configured in DT`.

The compatibility profile prefers 1280x720 at 60 Hz. It also advertises
720p50, 1080p24/25/30, 480p/576p, and legacy 640x480, 800x600 and 1024x768
at 60 Hz. All advertised pixel clocks are at most 74.25 MHz; the range
descriptor and HDMI TMDS limit are 80 MHz. HDR, deep color, interlaced
modes, 1080p60 and 4K are not advertised. Basic stereo audio is advertised
for HDMI source compatibility; this does not implement audio streaming.

Sources set to automatic display selection should negotiate a supported mode.
EDID cannot override a manually forced mode or a VGA converter that ignores
downstream EDID. After changing profiles, reconnect HDMI; a source may also
need its display settings reset to automatic. The profile is loaded on every
application service start and remains available when swapping source devices.
Some BIOS firmware may only read EDID at startup: restart the source PC with
HDMI connected to InfraBox if unplugging and reconnecting does not help.

On 2026-09-07 the profile was deployed to the active appliance and verified
to persist across an appliance restart. The operator confirmed BIOS video on
a directly connected PC after restarting that PC. The resulting timing was
not measured after that confirmation. Regression testing with the older VGA
PC and testing with PS5 remain pending.

For PS5 capture, disable HDCP in Settings > System > HDMI and use automatic
resolution. Protected media cannot be captured. This profile does not add
controller emulation or guarantee compatibility with every converter.

Validation: `edid-decode --check config/edid/infrabox-compat.hex` and
`pytest tests/test_capture_edid.py`. Confirm actual frames as well as
`/api/v1/video/status`: signal detection alone does not prove streaming works.

References:
- https://wiki.geekworm.com/X630
- https://docs.pikvm.org/edid/
- https://blog.playstation.com/2020/11/09/ps5-the-ultimate-faq/
