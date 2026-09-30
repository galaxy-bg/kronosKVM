# Display

The appliance at 192.168.1.102 uses a 160x128 SPI LCD, driven by
`/opt/infrabox-lcd/lib/LCD_1inch8.py`. Reset is BCM27, DC BCM25,
SPI bus/device 0/0 at 4 MHz, with no software backlight pin.

## Four-button local control

| Key | Function | BCM | Physical pin |
| --- | --- | --- | --- |
| K1 | Up | 5 | 29 |
| K2 | Down | 6 | 31 |
| K3 | OK | 13 | 33 |
| K4 | Back | 19 | 35 |
| Common | Ground | — | 30 |

This wiring assumes four independent normally-open contacts to common ground,
not a matrix or resistor-ladder keypad. Inputs use internal pull-ups; no external
3.3 V or 5 V supply is connected to the switches. GPIO Zero uses BCM numbering:
https://gpiozero.readthedocs.io/en/rtd/api_input.html

At LCD service startup, the existing UI InfraBox logo and `Booting...` are shown
for two seconds. This is a service-start splash, not a firmware/early-kernel
screen. The first screen is a scrollable main menu matching the web UI:
Dashboard, Sessions, Storage, Recovery, Remote Assist, Tasks, Services, Logs,
Settings. Four rows are visible; a green highlight, arrow and position counter
identify the selected item. Up/down moves selection, OK opens, Back returns.
Detail pages show live API summaries and scroll with up/down; OK refreshes.
Sessions shows saved profile information (not a live session count); Settings
shows network information. These summary pages do not modify settings.

Remote Assist offers enable/disable and its separate startup preference.
Select an action, press OK to review, then OK again within ten seconds to
confirm. Back cancels confirmation before leaving the section.
Input is debounced and accepted on release;
holding a key does not repeat actions. Keys held at startup must first be released.
The menu uses the existing localhost API and waits for the matching host result.
Stale status or pending work blocks changes. Enable requires an existing VPN profile.
The LCD shows actual VPN state, LAN IP, startup preference and action feedback.
The logo comes from `frontend/src/infrabox-logo-transparent.png` in the checkout;
deploy that asset alongside the Python files. If absent, the splash retains its
InfraBox text and boot message.

## Breadboard test and deployment

From `/opt/kronoskvm`, run `sudo python3 scripts/keypad-panel.py --test-buttons`
with the LCD/keypad service stopped. This prints key names and never calls the API.
The host needs gpiozero, Pillow, spidev and numpy (already installed on .102).

Copy the keypad/renderer Python files into the corresponding checkout paths.
LCD operation is opt-in: only on a physically equipped appliance, create
`/etc/kronoskvm/lcd.enabled` with `sudo touch /etc/kronoskvm/lcd.enabled`.
Without this file, the vendor driver, or `/dev/spidev0.0`, the service is skipped
and the runner exits before importing GPIO/LCD dependencies or touching GPIO.
SPI device presence does not prove that a display is attached: remove the marker
before removing the panel. Leave it absent on headless appliances such as .112.
The optional service does not restart on failure and must not be a required
dependency of the application or boot target.
Install `deploy/systemd/infrabox-lcd-keypad.conf` as
`/etc/systemd/system/infrabox-lcd.service.d/keypad.conf`, then run
`sudo systemctl daemon-reload` and `sudo systemctl restart infrabox-lcd`.
The existing vendor driver and original status script remain in place.
Rollback: remove this drop-in, daemon-reload and restart the same service.
Do not run a second LCD process concurrently.

For another LCD driver, use `Menu.lines()` or the runner's `--output` JSON file
(includes `updated_at`; consumers should reject old data). `--lcd` is specific
to the installed .102 panel. No arbitrary service stop/restart menu is exposed.
