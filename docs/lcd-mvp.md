# LCD MVP

The physical 160×128 LCD starts at Status. OK opens the main menu; Up/Down
navigate or scroll, OK selects, Back returns to the top-level menu. Back at the
top-level menu stays there. Thirty seconds without
input returns to Status unless an action is still running. Confirmations expire
after 15 seconds and always select Cancel initially. Choose Confirm with Up/Down
and press OK to submit. Result screens close with OK or Back.

```
Status
  System Ready / Error (failed service or unavailable control-plane data)
  Ethernet IPv4
  Wi-Fi AP ON / OFF
  Customer Access status
  VPN status
Network
  Network Diagnostics
  Wi-Fi AP Enable / Disable
  Customer Access Enable / Disable
Remote Assist
  VPN Status (state, address, profile)
  Connect / Disconnect (depending on enabled state)
System
  Device Information (hostname, model, full serial, uptime, application release)
  Service Health
  Restart
  Shutdown
```

KVM/console menus and the previous web-section mirror are removed. Status has
five rows; scroll down for VPN. Diagnostics checks Ethernet carrier, IPv4,
Ethernet default gateway and ICMP response, system DNS resolution of example.com,
and ICMP response from 1.1.1.1. An unanswered ping does not prove a network outage.
These are bounded host checks; the render/keypad loop remains responsive.

The root-only local controller uses a single background worker and fixed action
names, reusing the existing Wi-Fi/AP policy locks and the restricted localhost
LCD credential for Remote Assist. No additional HTTP permissions or administrator
credential storage were added. Customer Access retains the saved CIDR limits;
policy application failures fail closed. Wi-Fi AP is a runtime switch: normal
boot Wi-Fi provisioning restores the recovery AP, and a web Wi-Fi mode/password
change may also reactivate it. Wi-Fi disable disconnects associated clients;
Customer Access disable can interrupt clients reaching Ethernet through the AP.

Remote Assist requires a profile configured in the web UI. Connect waits for the
correlated host result and reports the actual state, including waiting_handshake;
queuing a request never implies that the VPN handshake completed. Restart and
Shutdown dispatch real host systemctl commands only after explicit confirmation.
Do not test them on a production target merely to verify navigation.

## Deployment — 2026-10-15

Installed on `192.168.31.26` (`infrabox-000865dd`) by updating four host LCD files
and restarting only `infrabox-lcd.service`. API/web/guacd images were unchanged.
Recovery archive:
`/var/backups/kronoskvm/pre-lcd-mvp-20261015.BC1PUa/lcd-source.tar.gz`.
To roll back, stop the LCD service, restore this archive under `/opt/kronoskvm`,
remove `backend/app/hardware/lcd_control.py`, and restart the LCD service.

Validation: the final full suite passed 221 tests. Lint and diff whitespace checks
pass.
Real device reads show the correct serial/model, IP, AP, Customer Access, VPN and
service health. Real diagnostic probes all passed. Actual DejaVu-rendered Status,
Network, Remote Assist, System and confirmation images were generated without a
second hardware driver and inspected. The sole LCD process starts on Status and
reports System Ready; application containers remain healthy, with no failed units.

VPN profile is absent on this device, so a real VPN connection was not exercised.
AP disable, Customer Access changes, Restart and Shutdown are covered with mocked
host operations; they were not triggered live to avoid interrupting the current
management path or appliance power. Physical button operation and panel visibility
still require an operator check.

## Physical navigation diagnosis — 2026-10-15

After a reboot the operator reported that selecting Network/Remote Assist/System
returned to Status. Added key-event logging to the sole LCD runner. The live
journal showed `Key down BCM6: ... Menu[0] -> Menu[1]`, then
`Key back BCM19: ... Menu[1] -> Status`. This was the Back input, rather than
an OK selection or idle timeout. The OK input is K3/BCM13; K4/BCM19 is Back.
Updated the deployed footer to explicitly show K3 for select and K4 for back.
A scanner-to-menu regression test covers entering all four sections and Back
returning to Status. Eighteen affected tests and lint passed. The LCD service
was restarted to load these changes; no appliance reboot was needed.

The subsequent navigation update makes Back always return to the top-level menu,
cancelling an open confirmation without submitting it. Repeated Back stays at the
menu; OK enters the highlighted section. Running operations continue in the
background. Nineteen affected tests and lint passed; deployed by LCD-service restart.

The final enclosure mapping follows the operator's physical button order:
K1 ↓ = BCM5, K2 ↑ = BCM6, K3 ✓ = BCM19 (menu/select), K4 ↩ = BCM13
(back to top level). This supersedes the earlier assumed K3/BCM13 and K4/BCM19
mapping recorded in the diagnostic history above. The LCD footer uses symbols
instead of K numbers, matching the planned enclosure markings. The update passed
27 affected tests and lint. Previous keypad/renderer files are backed up at
`/var/backups/kronoskvm/lcd-key-symbols-20261015`.

## Footer label correction — 2026-11-01

Corrected the repeated Menu label: the select key shows `✓ Menu` on status/detail
screens and `✓ Select` in selectable menus; the back key shows `↩ Back`.
GPIO assignments and navigation behavior remain unchanged. Deployed to
`192.168.31.27` by restarting only `infrabox-lcd.service`; the previous renderer
is at `/var/backups/kronoskvm/lcd-back-label-20261101/lcd_panel.py`.
The 27 keypad, LCD-control and optional-LCD tests passed. Physical button feedback
can now be checked on the installed four-button board.
