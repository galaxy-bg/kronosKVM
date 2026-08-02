# Network Design

Native Ethernet is the customer/development uplink. Integrated Wi-Fi provides a
persistent local management access point at `192.168.34.100/24`.

## Active prototype

- Ethernet interface: `eth0`, DHCP from the connected LAN
- Last development address: `192.168.31.185/24`
- Management AP interface: `wlan0`
- Management SSID: `KronosDX-iKVM`
- Appliance AP address: `192.168.34.100/24`
- Routing, NAT and bridging: disabled
- Web UI: reachable through both Ethernet and the management AP
- API: localhost only behind Nginx

The AP is intentionally open during prototype development. Production requires
an approved authentication and wireless-security policy.

## Operational policy

Use Ethernet for OS updates, package downloads, Git operations and container
image pulls. Keep the management AP available as the local recovery path. Never
change Ethernet and AP configuration in the same unverified transaction.

An optional USB Ethernet adapter may later use the blue Service USB 3.0 port;
it must not replace the native management path until its interface role and
firewall policy are explicitly configured.
