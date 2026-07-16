# Physical Port Map

The chassis port tested by the operator as ETH0 is confirmed as Linux `eth0`.
The initial inventory also discovered a USB RTL8152 `eth1`, whose chassis label
remains unverified.

| Chassis label | Proposed function | Verification |
|---|---|---|
| ETH0 | Management/customer LAN | Confirmed as Linux `eth0` on 2026-07-16 |
| ETH1 | Target/service LAN | Confirmed as USB path `1-1.5`, RTL8152 |
| USB1 / Console 1 | Serial adapter 1 | Confirmed as USB path `1-1.1` |
| USB2 / Console 2 | Serial adapter 2 | Confirmed as USB path `1-1.2` |
| USB3 / Service USB | Expansion/maintenance | Confirmed as USB path `1-1.3` |
| USB-C SLAVE / KVM OTG | HID and virtual media | Physical mux behavior confirmed; UDC enablement pending |
| CAM0 | Primary capture | Waiting for HDMI-to-CSI module |
| CAM1 | Future capture | Waiting for hardware |
| DISP | Local display | Inspect DSI/device tree |

Interface names must not be changed until physical mapping is complete.

During verification, `eth0` received `192.168.31.144/24` by DHCP and became the
preferred default route. Independent SSH access over Ethernet was successful.

## USB topology

The three chassis USB host ports and ETH1 are connected through the internal
7-port USB 2.0 hub:

| Product name | Chassis label | Stable physical USB path |
|---|---|---|
| Console 1 | USB1 | `1-1.1` |
| Console 2 | USB2 | `1-1.2` |
| Service USB | USB3 | `1-1.3` |
| Target/service LAN | ETH1 | `1-1.5` |

The paths were verified by moving the same known HID dongle between USB1,
USB2 and USB3.

Connecting the USB-C `SLAVE` port removes the internal hub and USB ETH1 from
the running host topology. Disconnecting it restores them. This indicates a
carrier-level host/device mux and means simultaneous KVM OTG plus USB1-3/ETH1
operation must not be assumed. The current boot configuration still uses
`otg_mode=1`; the DWC2 peripheral overlay and UDC remain pending.
