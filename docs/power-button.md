# Power button integration status

The operator selected the **Witty Pi 4 onboard button**, not a separate GPIO
button. The USB power adapter feeds Witty; the Pi OTG input is not used.
Programmer availability and the installed MCU firmware revision remain
unconfirmed. The onboard behavior below is a target, not a deployed feature.

The separate-button runner documented below is an unused prototype. Do not
install it for the onboard switch: it deliberately rejects Witty GPIO4.
Onboard integration requires a reviewed MCU firmware change and a compatible
Linux handler, retaining alarm/voltage protections and shutdown/reboot power
coordination. No firmware has been flashed and no power-button service enabled.

## Separate GPIO prototype (not selected)

Implementation is prepared; hardware wiring is not yet confirmed and the
service is not installed/enabled on the appliance. It does not change Witty Pi's
firmware or onboard switch behavior.

## Gestures while the OS is running

The action is chosen only after a stable release:

| Hold duration | Action |
| --- | --- |
| Less than 2 seconds | No action |
| 2 seconds to less than 5 seconds | `systemctl reboot` |
| 5 seconds or more | `systemctl poweroff` |

Crossing two seconds while still holding never triggers reboot. Startup holds
are ignored until a release arms the button. A 50 ms debounce filters contact
bounce; one release triggers at most one request. A successful request latches
the runner off while systemd proceeds with the action.

The LCD displays the hold duration and the action that releasing will select.
Missing/stale runtime feedback leaves the normal menu unchanged. This overlay
is display-only; no file contents can trigger a power action.

## Witty Pi 4 constraints

The operator identifies the board as Witty Pi 4 HAT RTC, marking `P5704B`.
The second appliance currently has no `/opt/wittypi` software or `wittypi.service`.
Its Linux I2C adapter list also lacks the usual I2C1 device, so hardware
identification, I2C provisioning and the actual power path still need checking.

The manufacturer's firmware handles the onboard button in the MCU, and can
force power removal during a hold. A Linux hold timer cannot override that.
The stock daemon also responds directly to GPIO4 falling. Therefore this
implementation requires a separate normally-open GPIO button to GND, with an
internal pull-up, on a confirmed unused BCM pin. It rejects reserved pins,
including Witty GPIO4/GPIO17, LCD, keypad, SPI and I2C pins.

The dedicated button cannot turn on an unpowered Pi. Keep the Witty switch for
that purpose until a separately reviewed hardware/firmware design integrates
both functions. An OS shutdown is not proof that Witty has removed the supply;
that also depends on its provisioning and the power wiring.

References: [official Witty Pi 4 firmware](https://github.com/uugear/Witty-Pi-4/blob/main/Firmware/WittyPi4/WittyPi4.ino),
[official daemon](https://github.com/uugear/Witty-Pi-4/blob/main/Software/wittypi/daemon.sh).

## Provision after wiring is confirmed

1. Select an unused BCM pin and verify continuity/button behavior without
   invoking power actions. GPIO26 (physical pin 37) is an example candidate,
   not confirmed wiring. Connect the button's other contact to a GND pin.
2. Run `sudo python3 /opt/kronoskvm/scripts/power-button.py --pin BCM_NUMBER --dry-run`
   and verify short, medium and long holds. Dry run never calls systemctl.
3. Install `deploy/systemd/infrabox-power-button.service`, set the confirmed pin
   in `/etc/kronoskvm/power-button.env` as `KRONOSKVM_POWER_BUTTON_PIN=BCM_NUMBER`,
   create `/etc/kronoskvm/power-button.enabled`, reload systemd and enable/start
   the service.
4. Verify LCD feedback, safe restart and safe shutdown/power recovery with the
   operator present. These physical tests remain pending.

The service maintains `/run/kronoskvm-power-button/status.json` in a root-owned
runtime directory. It uses host gpiozero and the local hardware module; the
application API's admin password is not needed or stored.
