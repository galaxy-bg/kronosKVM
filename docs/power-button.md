# Power button integration status

The operator selected the **Witty Pi 4 onboard button**, not a separate GPIO
button. The USB power adapter feeds Witty; the Pi OTG input is not used.
The custom hold-duration behavior below is a target, not a deployed feature.
Live read-only identification on 2026-10-16 found Witty Pi 4 firmware ID `0x26`,
revision `0x07`; no firmware was flashed.

The separate-button runner documented below is an unused prototype. Do not
install it for the onboard switch: it deliberately rejects Witty GPIO4.
The custom hold-duration behavior requires a reviewed MCU firmware change and a
compatible Linux handler, retaining alarm/voltage protections and shutdown/reboot
power coordination. Standard manufacturer button behavior uses its ordinary host
software and does not require this custom gesture firmware. No power-button
custom gesture service has been enabled.

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
At the original inspection the second appliance had no `/opt/wittypi` software
or `wittypi.service`, and I2C1 was disabled. The standard integration described
below was subsequently provisioned on 2026-10-16.

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

## Live inspection — 2026-10-16

Inspection of the Ethernet appliance confirmed:

- Debian 13 ARM64 on Raspberry Pi 4; GPIO2/3 are unused inputs at baseline.
- I2C1 is disabled in boot configuration. GPIO4/17 are not claimed by LCD or
  keypad services. The standard model does not use the L3V7 charging-status
  GPIO5/6 features, which would conflict with this keypad.
- A temporary runtime `i2c1` overlay exposed `/dev/i2c-1`. Targeted register
  reads at address `0x08` returned firmware ID `0x26` and revision `0x07`.
- RTC registers returned a 2000-01-26 calendar and an oscillator-stop flag.
  Correct time and retention must be qualified after initialization.
- The MCU proxies RTC registers; an absent `/dev/rtc*` alone does not prove
  Witty Pi hardware is absent. The current generic API only checks Linux RTC
  device nodes, so it needs Witty-specific status for this board.
- The manufacturer host daemon is absent, as are WiringPi and any enabled
  custom physical power-button service. Web/LCD systemd power actions are
  separate and remain available.

Only identification/status registers were read. No RTC/config register writes,
clock changes, button tests, firmware updates, power actions or persistent boot
changes were made. The temporary overlay was removed after diagnosis.

### Proposed implementation

1. Back up boot configuration and provision persistent I2C1 on GPIO2/3.
2. Install a pinned, reviewed manufacturer software version and compatible
   GPIO tooling. Use one service owner; do not combine the vendor SysV runner
   with the existing project systemd template. Avoid unrelated installer
   changes such as adding another web interface.
3. Initialize the board RTC from NTP-synchronized system time; record whether
   RTC uses UTC or local time, and keep read/write conversions consistent.
   Do not set the system clock from the uninitialized 2000 RTC.
4. Integrate board presence, RTC validity and host-daemon state separately
   into Services/hardware status. Preserve the distinction between absent
   software and absent hardware.
5. Validate GPIO4 idle level, GPIO17 handshake and saved alarm settings before
   starting the daemon. Complete physical shutdown/power-on and clock-retention
   tests with an operator present. Custom short/long holds remain separate.

References: [manufacturer register map](https://github.com/uugear/Witty-Pi-4/blob/main/Software/wittypi/utilities.sh),
[host daemon](https://github.com/uugear/Witty-Pi-4/blob/main/Software/wittypi/daemon.sh),
[installer](https://github.com/uugear/Witty-Pi-4/blob/main/Software/install.sh).

## Standard Witty Pi 4 integration — 2026-10-16

`sudo bash /opt/kronoskvm/scripts/install-wittypi.sh` provisions the standard
board after checking firmware ID `0x26`. It pins manufacturer commit
`d466cbc18aaea619c1f41ddb170789a661be3338` (software 4.23) and official
WiringPi 3.20 ARM64, checking SHA-256 before installation. It does not flash
MCU firmware or install the manufacturer's extra web interface.

The single owner is `wittypi.service`. Its preflight verifies the released
GPIO4 button and idle-high UART TXD on GPIO14. GPIO17 carries the standard
SYS_UP handshake. L3V7 is rejected because its GPIO5/6 conflict with this
appliance's keypad. The clock is stored in UTC; NTP is preserved. When NTP
is available the helper initializes RTC from it; valid RTC may seed system
time at boot when NTP is not synchronized. Invalid RTC never sets system time.

The installer backs up boot settings, enables I2C1 and UART, removes the
serial login console from the dedicated UART, and stages `miniuart-bt` to
preserve UART0 for Witty's OS power-state signal. Some current kernels cannot
apply that overlay at runtime: the installer then leaves the daemon stopped
and reports REBOOT_REQUIRED. Review and perform a controlled reboot; it is
never issued automatically by the installer. Do not drive TXD low or remove
its UART overlay while Witty's daemon has already sent SYS_UP.

The public `/state/wittypi-status.json` snapshot is refreshed by the existing
service-status helper. The RTC API now reads this fresh MCU snapshot before
falling back to ordinary `/dev/rtc*` devices. Services shows the actual systemd
state plus firmware revision and RTC UTC time.

Custom 2–5 second reboot / longer-hold shutdown gestures are not deployed;
this integration follows manufacturer button behavior. Physical cutoff,
power-on, and clock retention after full power removal need an operator test.

### Deployment result — 2026-10-16

Standard Witty Pi integration is deployed and `wittypi.service` is enabled and
active after a controlled reboot. The daemon reports manufacturer software 4.23,
firmware ID 0x26 / revision 0x07, the GPIO17 SYS_UP handshake, and waits for the
GPIO4 shutdown input. GPIO14 is UART TXD0 and idle high. I2C1 is persistent.
RTC was initialized from synchronized system time and remains valid in UTC,
with approximately one second of observed read-time difference. At boot the
valid RTC seeded system time; NTP remained enabled and later synchronized.
Services and the hardware API show the real board/RTC data.

An initial host-helper import traversed application dependencies not installed
on the host. It was corrected to import the standalone, standard-library-only
register decoder directly, with an isolated Python regression check. The runtime
miniuart-bt overlay is rejected by this kernel, so UART was activated through
backed-up boot settings and a controlled reboot instead.

The existing VPN profile and autostart preference were verified against their
pre-reboot baseline. Since the previous session was connected with autostart
disabled, the same VPN connection was restored after reboot. No MCU firmware
was flashed, scheduled alarms were not configured, and the physical button
was not pressed. Physical shutdown/cutoff, restart/power-on behavior and RTC
retention with all external power removed remain operator qualification tests.

Validation: 289 automated tests, Python lint and shell syntax checks passed.
API/web/guacd and LCD are healthy after reboot; no failed units were reported.
