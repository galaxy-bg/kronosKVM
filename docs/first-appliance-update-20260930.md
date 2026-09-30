# First appliance update — 2026-09-30

Updated the application under `/opt/kronoskvm` on `192.168.1.112`
(`kdx-infrabox`) from the local workspace and rebuilt API/web images.
No OS upgrade was performed. Runtime settings and Recovery data were retained.
Backup is on-device at `/var/backups/kronoskvm/pre-update-20260930/application`;
previous images are tagged `pre-update-20260930` for both API and web.

LCD is opt-in via `/etc/kronoskvm/lcd.enabled`, with additional driver and SPI
checks. The marker and LCD service are absent on this appliance. Direct execution
of `keypad-panel.py --lcd` exits successfully before GPIO/LCD imports. The LCD
drop-in now has matching systemd conditions and disables automatic restart.
An SPI node is not physical panel detection; provisioning must reflect hardware.

Validation: 104 local tests passed, focused lint passed. After an actual reboot,
API health and HTTPS health returned success, no systemd units failed,
containers and dnsmasq were active, and the headless LCD check passed again.

KVM capture device exists, but no HDMI signal is detected. Before update,
TC358743 status explicitly reported no cable +5V and no TMDS signal. HID keyboard
and mouse devices are ready; the USB controller reports `configured` after boot.
Target-side input and end-to-end video remain unverified. Check the source video
output, cable, and any VGA-to-HDMI converter/power before further video diagnosis.
Recovery HTTP/FTP/TFTP services were inactive before update; this rollout did not
activate them or test file transfers.

Later validation after operator cable/source checks: HDMI reported 1280×720 at
60 Hz and the live JPEG endpoint returned HTTP 200 with a current frame. The
operator confirmed video returned. An earlier power loss during OTG removal
remains unexplained; subsequent reconnects did not reproduce it.

Recovery DHCP observation history, CSV export, confirmed history clearing and
10-second visible-view refresh were subsequently deployed. All 107 tests passed;
live CSV export returned the 10 retained observations. Clearing history preserves
active DHCP leases. Network forms with unsaved edits are protected from automatic
refresh. API/HTTPS health passed and systemd reported no failed units.
