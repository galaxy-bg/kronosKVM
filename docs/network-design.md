# Network Design

Native Ethernet is the customer/development uplink. Integrated Wi-Fi provides a
persistent local management access point at `192.168.34.100/24`.

## Active prototype

- Ethernet interface: `eth0`, DHCP from the connected LAN
- Ethernet address: DHCP-assigned; read the current address from Dashboard
- Management AP interface: `wlan0`, joined to `br-recovery` on the active appliance
- Management SSID: `KronosDX-iKVM`
- Appliance AP address: `192.168.34.100/24`
- Recovery bridge: `br-recovery`, combining management Wi-Fi and the configured Service interface
- No customer-LAN/WAN forwarding or NAT is enabled by Remote Assist
- Web UI: HTTP/HTTPS through Ethernet and the management AP; also through the VPN when connected
- API: localhost only behind Nginx

The AP is intentionally open during prototype development. Production requires
an approved authentication and wireless-security policy.

## Operational policy

Use Ethernet for OS updates, package downloads, Git operations and container
image pulls. Keep the management AP available as the local recovery path. Never
change Ethernet and AP configuration in the same unverified transaction.

Settings can apply DHCP or validated static IPv4, gateway and DNS values to
physical Ethernet and future USB-Ethernet interfaces through a constrained
NetworkManager host helper. `wlan0` and the management AP are protected from
this API. An Ethernet change may disconnect the active browser session; use the
AP at `192.168.34.100` as the recovery path.

The Service USB Ethernet adapter belongs to the Recovery bridge. It must not
silently become a customer-network WAN interface.

## USB WAN and Remote Assist

The Storage/WAN port supports phone USB tethering. Its DHCP profile uses metric
600; native Ethernet uses metric 100 and is preferred. USB becomes the default
uplink when the Ethernet default route disappears. A connected Ethernet link
with an unusable upstream does not automatically trigger failover.

Remote Assist manages the `wg-kdx` WireGuard interface separately. The first
version supports one private-IPv4 peer profile and does not add forwarding,
NAT, a public reverse proxy or per-user web authentication. Fresh handshakes,
traffic counters and the configured VPN address appear in the Remote Assist
page and physical-port status dialog.

See [USB WAN](usb-wan.md) and [Remote Assist](remote-assist.md) for installation,
configuration limits and validation evidence.
