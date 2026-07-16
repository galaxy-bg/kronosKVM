# Port Plan

| Port | Purpose | Initial state |
|---|---|---|
| 22/TCP | SSH administration | Enabled |
| 80/TCP | HTTPS redirect | Future |
| 443/TCP | Web interface | Future |
| 5900/TCP | VNC compatibility | Disabled |
| 6080/TCP | noVNC development | Localhost only |
| 8000/TCP | FastAPI development | Localhost only |
| 2001/TCP | Serial channel 1 | Disabled |
| 2002/TCP | Serial channel 2 | Disabled |
| 5353/UDP | mDNS | Disabled |
| 9100/TCP | Metrics | Disabled |
| 8554/TCP | Optional RTSP | Disabled |

Only SSH should be remotely reachable during initial discovery.

The management AP uses DHCP UDP 67 and DNS TCP/UDP 53 only on `wlan0`; DNS also
listens on loopback for the appliance resolver. No customer-network forwarding,
default gateway advertisement or NAT is enabled.
