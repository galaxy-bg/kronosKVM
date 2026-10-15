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

## Physical buttons

| Button | Symbol | Action | BCM |
| --- | --- | --- | --- |
| K1 | ↓ | Down | 5 |
| K2 | ↑ | Up | 6 |
| K3 | ✓ | Menu / Select | 19 |
| K4 | ↩ | Return to top-level menu | 13 |

The LCD footer uses these symbols for enclosure markings. Reload changes by
restarting `infrabox-lcd.service`; an appliance reboot is unnecessary.
