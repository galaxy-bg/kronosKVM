# Physical Port Map

The active prototype uses four independent USB-A host ports plus the separate
USB-C DWC2 controller in device mode.

| Physical port | Role | Linux topology |
|---|---|---|
| Black USB-A 2.0 #1 | Console 1 | `1-1.3` |
| Black USB-A 2.0 #2 | Console 2 | `1-1.4` |
| Blue USB-A 3.0 #1 | Service USB / optional USB Ethernet | `1-1.1` at USB 2 speed, `2-1` at SuperSpeed |
| Blue USB-A 3.0 #2 | External Storage | `1-1.2` at USB 2 speed, `2-2` at SuperSpeed |
| USB-C | KVM OTG | UDC `fe980000.usb` |
| CSI-2 | X630 video | `/dev/video0` |
| RJ45 | Customer/development Ethernet | `eth0` |

A USB 2 device connected to a blue USB 3 port appears on its USB 2 companion
path. That does not make the physical socket a USB 2-only port.

The console mappings were verified by moving the PL2303 adapter between the
black sockets. Console identity should prefer `/dev/serial/by-id` when a serial
number is present; topology is the physical-role fallback.
