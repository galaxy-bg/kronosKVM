# Remote Assist

The Remote Assist page manages one active office/customer WireGuard profile,
USB phone WAN status, the VPN switch, a separate startup preference, last
handshake, transfer counters and the private HTTPS access address.

## Architecture and installation

- API: `/api/v1/remote-assist` reads a sanitized host status snapshot.
- `PUT /profile` accepts validated manual settings or a `.conf` import.
- `POST /enable`, `/disable`, `/boot-on`, `/boot-off` enqueue a bounded action.
- A systemd path/service consumes the request under a shared file lock.
- A five-second timer publishes current WAN, uplink and WireGuard state.
- NetworkManager owns the `KDX-Remote-Assist` / `wg-kdx` interface.

Install from `/opt/kronoskvm` with `sudo bash scripts/install-remote-assist.sh`.
The installer adds `wireguard-tools` if missing. The first installation is off
with startup autoconnection disabled. The API container remains unprivileged.

The host saves configuration under `/etc/kronoskvm/remote-assist` (directory
0700, files 0600). Its NetworkManager keyfile is root-readable only. Submitted
keys pass through a 0600 request file that is removed after processing. Private
and preshared keys are never returned in status or included in command-line
arguments. Invalid configuration errors do not echo submitted content.

## Behavior

Enable without a profile shows Setup required; a first profile can then be saved
and activated. Replacing an existing profile requires switching Remote Assist
off. Disable removes the active VPN and disables NetworkManager autoconnection,
while retaining the profile and the separate startup preference. Startup
reconnect requires BOTH enabled and autostart. Without autostart the next boot
resets the switch to off.

Connected means a handshake within the last 180 seconds, not just an interface
being up. No handshake/stale handshakes are shown as Waiting for VPN handshake.
Status older than 30 seconds disables controls rather than claiming success.
Actions return 202 first; the page waits for the host result before completing.

USB IP assignment is shown as USB network ready, not proof of internet access.
The existing system route priority applies: Ethernet preferred, phone fallback
when the Ethernet default route disappears. Internet-health-based failover and
uplink-specific DNS selection are not implemented yet.

## Supported profiles and limits

The first version supports one peer, RFC1918 IPv4 tunnel addresses and specific
RFC1918 peer networks. Private key, server public key, optional preshared key,
endpoint and keepalive are supported. Imports reject hooks, DNS overrides,
unknown fields, multiple peers, full-tunnel and IPv6 configurations. The host
rejects routes/address conflicts with existing appliance networks. The assigned
VPN interface address uses /32; peer routes determine VPN reachability.

No LAN bridging, forwarding, NAT or public reverse proxy is configured. Office
peers/server routing and firewalls must permit access to the device's VPN IP.
The URL uses the existing appliance HTTPS service and certificate. This module
does not add per-user web authentication: it inherits the existing appliance
access model, so access should be limited to trusted VPN peers.

Multiple saved customer profiles, VPN server provisioning, public browser-only
access and VPN-specific login/authorization remain future work.

## Validation

2026-09-22: the local suite passed 87 tests (with the existing 1 GiB local storage
reserve override). Browser checks covered 390px mobile and 1440px desktop,
including toggle completion and no horizontal page overflow. On the appliance,
a temporary loopback WireGuard peer completed a real handshake; status reported
Connected, startup preference changed correctly, Disable removed the tunnel and
autoconnection, and default routes stayed unchanged. Test keys, interface and
profile were removed. This is not an off-site/customer VPN connectivity test;
that requires the user's server profile.

## Physical port UI

The shared port is labelled External Storage / WAN. Both the state badge and
the Status menu open a refreshable dialog showing the detected USB device,
interface, addresses and gateway, plus separate VPN state, configured VPN IP,
preferred uplink and last handshake. VPN status is shown independently of USB
attachment, since the tunnel may use Ethernet. The frontend combines existing
port and Remote Assist APIs, so this display update can ship without restarting
the API or changing an installed VPN profile.
