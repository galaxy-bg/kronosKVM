# Network Design

Chassis ETH0 is the primary development, update and deployment connection.
The permanent Wi-Fi AP is an isolated local recovery path and must remain
available at `192.168.34.100`.

Do not assume other chassis Ethernet labels match Linux interface names until
they are physically verified.

## Confirmed Ethernet backup

The chassis ETH0 port is confirmed as Linux `eth0`. With a customer/LAN cable
connected it received `192.168.31.144/24` by DHCP, gateway and DNS
`192.168.31.1`, and became the preferred default route. SSH and the API service
were independently verified through this Ethernet path.

This provides the rollback path required before converting `wlan0` into the
persistent KronosKVM management access point.

## Development connection policy

Connection preference:

1. `kronoskvm.local` over ETH0 when mDNS is available.
2. The current ETH0 DHCP address.
3. `192.168.34.100` through the KronosKVM AP for local fallback.

Use ETH0 for operating-system updates, package installation, GitHub access,
source pulls, container image pulls and other outbound internet traffic. Do not
use the isolated AP for routine development updates.

Normal deployment operations must never stop, restart or reconfigure hostapd,
dnsmasq or the permanent AP. Before a network change, verify a second working
management path. ETH0 and Wi-Fi configuration must never be changed in the same
transaction:

- verify AP access before restarting or changing ETH0;
- verify ETH0 SSH access before changing the AP;
- validate configuration files before rebooting.

The development SSH alias is:

```sshconfig
Host kronoskvm
    HostName kronoskvm.local
    User kronosdx
    IdentityFile ~/.ssh/kronoskvm_ed25519
    IdentitiesOnly yes
    ServerAliveInterval 30
    ServerAliveCountMax 3
```

If mDNS is temporarily unavailable, replace `HostName` with the current ETH0
DHCP address. Do not point the normal development alias at the isolated AP.

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

## Status command

Run:

```bash
kronoskvm status
```

The command reports AP service/address state, ETH0 link and address, default
gateway, DNS servers, ETH0 internet reachability and container runtime state.
It reads no hostapd secret, environment credentials or application tokens.
