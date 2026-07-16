# Network Design

Initial management address: `192.168.31.145/24` is currently assigned to
`wlan0`, not Ethernet. The default route uses `192.168.31.1`.

- Management interface: existing Wi-Fi LAN; SSH is the only remote TCP listener.
- Service interface: unconfigured; no DHCP, bridge, routing or forwarding.
- Portable AP and controlled bridge modes are future explicit features.

Do not assume chassis ETH labels match Linux interface names.

The initial inventory found `eth0` and `eth1` down with no carrier. UDP 5353 was
listening even though the proposed KronosKVM configuration disables mDNS; this
existing OS behavior will be reviewed without changing it during discovery.

## Confirmed Ethernet backup

The chassis ETH0 port is confirmed as Linux `eth0`. With a customer/LAN cable
connected it received `192.168.31.144/24` by DHCP, gateway and DNS
`192.168.31.1`, and became the preferred default route. SSH and the API service
were independently verified through this Ethernet path.

This provides the rollback path required before converting `wlan0` into the
persistent KronosKVM management access point.

## Persistent management access point

Planned and implemented settings:

- SSID: `kronosKVM`
- Interface: `wlan0`
- Appliance address: `192.168.34.100/24`
- DHCP pool: `192.168.34.150-192.168.34.220`
- WPA2-PSK with a secret entered interactively during installation
- DNS forwarding listens only on loopback and the AP address
- No default gateway is advertised to AP clients until controlled NAT is enabled
- Routing, NAT and bridging disabled
- `eth0` remains the customer network and internet uplink

The WPA passphrase is not present in Git or documentation. Use
`scripts/rollback-network.sh` over Ethernet to return `wlan0` to client mode.
