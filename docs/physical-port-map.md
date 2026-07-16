# Physical Port Map

The chassis port tested by the operator as ETH0 is confirmed as Linux `eth0`.
The initial inventory also discovered a USB RTL8152 `eth1`, whose chassis label
remains unverified.

| Chassis label | Proposed function | Verification |
|---|---|---|
| ETH0 | Management/customer LAN | Confirmed as Linux `eth0` on 2026-07-16 |
| ETH1 | Target/service LAN | USB RTL8152 exists; chassis mapping pending |
| USB1 | Serial adapter 1 | Known-device USB topology test |
| USB2 | Serial adapter 2 | Known-device USB topology test |
| USB3 | Expansion | Known-device USB topology test |
| SLAVE | USB OTG/device | UDC directory empty; controller investigation pending |
| CAM0 | Primary capture | Waiting for HDMI-to-CSI module |
| CAM1 | Future capture | Waiting for hardware |
| DISP | Local display | Inspect DSI/device tree |

Interface names must not be changed until physical mapping is complete.

During verification, `eth0` received `192.168.31.144/24` by DHCP and became the
preferred default route. Independent SSH access over Ethernet was successful.
