# Physical Port Map

Chassis-to-Linux mappings remain unverified. The initial inventory discovered a
native `eth0` and a USB RTL8152 `eth1`, both without carrier.

| Chassis label | Proposed function | Verification |
|---|---|---|
| ETH0 | Management LAN | Native CM4 Ethernet exists; chassis mapping pending |
| ETH1 | Target/service LAN | USB RTL8152 exists; chassis mapping pending |
| USB1 | Serial adapter 1 | Known-device USB topology test |
| USB2 | Serial adapter 2 | Known-device USB topology test |
| USB3 | Expansion | Known-device USB topology test |
| SLAVE | USB OTG/device | UDC directory empty; controller investigation pending |
| CAM0 | Primary capture | Waiting for HDMI-to-CSI module |
| CAM1 | Future capture | Waiting for hardware |
| DISP | Local display | Inspect DSI/device tree |

Interface names must not be changed until physical mapping is complete.
