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
