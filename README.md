# KDX InfraBox

**KronosDX · Infrastructure in a Box**

Portable access, recovery and remote assistance. Hardware validation and
repeatable installation work are ongoing; this is not yet a production-qualified release.

The product is **KDX InfraBox**. The GitHub repository remains
[`galaxy-bg/kronosKVM`](https://github.com/galaxy-bg/kronosKVM), and existing
`kronoskvm-*` service names and `/opt/kronoskvm` paths are retained for
compatibility. See [product naming](docs/product-naming.md).

KDX InfraBox is a portable, browser-managed IP-KVM and infrastructure-access
appliance developed by KronosDX. The current prototype combines HDMI capture,
USB keyboard and mouse emulation, two serial-console ports, staging storage,
network connections, session logging and a permanent local management access
point.

Product descriptor: **Infrastructure in a Box**.

> HTTPS is implemented. Per-user web authentication and a production access
> policy are still pending. Remote Assist provides VPN connectivity, not a
> separate web login or public access gateway.

## Current prototype

- Raspberry Pi 4 Model B Rev 1.5, aarch64
- 64 GB microSD; 32 GiB logical internal staging pool
- Geekworm X630 HDMI-to-CSI bridge on CSI-2
- USB-C DWC2 controller in peripheral/device mode for KVM OTG
- Two black USB-A 2.0 ports assigned to Console 1 and Console 2
- Two blue USB-A 3.0 ports assigned to Service/Recovery and External Storage / WAN
- Native Ethernet for customer/development access
- Integrated Wi-Fi management AP at `192.168.34.100/24`
- Debian GNU/Linux 13 with Raspberry Pi kernel `6.18.34+rpt-rpi-v8`
- GPIO 5V prototype power; RTC/power-control board pending

Ethernet DHCP and VPN addresses are installation-specific. Use the current
Dashboard and Remote Assist status rather than an address from a historical log.

HDMI compatibility now defaults to 720p60, with 1080p30 and legacy PC modes
available through the persistent EDID profile. A directly connected PC's BIOS
video was confirmed by the operator after restarting the source PC with HDMI
attached. Some firmware reads EDID only at startup; reconnecting HDMI alone may
not update its output mode. See [capture compatibility](hardware/capture/README.md)
for supported modes and PS5 setup. VGA regression and PS5 testing with this
profile are still pending.

## Verified functionality

- X630 HDMI capture on `/dev/video0` with live MJPEG browser streaming
- Browser keyboard and BIOS-compatible relative mouse over USB-C OTG
- Pi 4 DWC2 gadget profile with two HID interfaces:
  - `/dev/hidg0`: keyboard
  - `/dev/hidg1`: boot-compatible relative mouse
- Independent USB-A host ports while USB-C operates in device mode
- Serial-console discovery, auto-baud, interactive terminal and temporary logs
- Saved SSH, Telnet, RDP, VNC and web connection profiles without passwords
- Internal 32 GiB staging area with upload, drag-and-drop, download and delete
- Background upload tasks, progress, cancellation and incomplete-fragment cleanup
- Structured application/audit logs and temporary downloadable session logs
- Safe UI-triggered appliance reboot and shutdown through an allow-listed host helper
- Management UI reachable through Ethernet and the permanent Wi-Fi AP
- Mobile layouts and a KVM Caps Lock control
- External USB file browsing, copy-to-stage and Copy & Mount
- Internal Storage SHA256 calculation and reference comparison
- Recovery publication with on-demand FTP, TFTP and HTTP downloads
- Phone USB tethering on the Storage/WAN port, with DHCP and WAN status
- Remote Assist: WireGuard configuration import/manual entry, enable/disable,
  startup preference, handshake/traffic status and a VPN access address
- Clickable physical-port status showing USB IP/gateway and separate VPN state

Staged ISO and IMG files can be presented to the target as read-only USB
virtual media and ejected without rebuilding the keyboard/mouse gadget.

## Physical port assignment

| Physical port | Appliance role | Verified topology |
|---|---|---|
| Black USB-A 2.0 #1 | Console 1 | `1-1.3` |
| Black USB-A 2.0 #2 | Console 2 | `1-1.4` |
| Blue USB-A 3.0 #1 | External Storage / WAN (USB drive or phone tethering) | USB 2 companion `1-1.1`, SuperSpeed `2-1` |
| Blue USB-A 3.0 #2 | Service / Recovery USB Ethernet | USB 2 companion `1-1.2`, SuperSpeed `2-2` |
| USB-C | KVM OTG device | DWC2 UDC `fe980000.usb` |
| CSI-2 | X630 video capture | `/dev/video0`, TC358743 |
| RJ45 | Customer/development LAN | Linux `eth0` |
| Wi-Fi | Local management AP | `192.168.34.100/24` |

See [physical port map](docs/physical-port-map.md),
[hardware notes](docs/hardware.md), [USB gadget design](docs/usb-gadget.md)
and [video capture](docs/video-capture.md).

## Power and OTG notes

The prototype is currently powered through GPIO 5V so the USB-C connector can
be used for OTG. Do not directly combine independent 5V sources without
backfeed protection. During prototype testing the most reliable sequence is:

1. power and boot the appliance;
2. power the target computer;
3. attach the USB-C OTG data cable.

The final RTC/power board must provide proper isolation or controlled power
sequencing between the appliance supply and target USB VBUS. A plain cut-VBUS
cable is not automatically suitable because DWC2 may require VBUS sensing.

Use **Settings → Reboot** for normal remote restarts. **Power off** performs a
safe shutdown, but the current GPIO supply must be physically cycled to start
the appliance again.

## Architecture

KDX InfraBox uses a hybrid host/container architecture:

- `kronoskvm-api`: FastAPI control plane, KVM/serial sessions, logs and storage
- `kronoskvm-web`: Nginx-hosted browser UI and reverse proxy
- host systemd helpers: capture initialization, ConfigFS USB gadget, power
  actions, networking and container lifecycle
- NetworkManager: Ethernet, Wi-Fi/recovery bridge, USB WAN and WireGuard profiles
- dnsmasq: recovery-network address and file-transfer services

The API binds to `127.0.0.1:8000`; Nginx is the network-facing gateway. The API
container runs non-root with a read-only root filesystem, dropped capabilities
and narrowly scoped device access. No Docker socket is exposed.

See [architecture](docs/architecture.md),
[containerization](docs/containerization.md), [API](docs/api.md),
[logging](docs/logging.md) and [security](docs/security.md).

## Repository layout

- `backend/` — FastAPI API, hardware adapters and tests
- `frontend/` — browser management interface
- `config/` — configuration examples
- `scripts/` — installation, inventory and host hardware helpers
- `deploy/` — systemd, Nginx, Docker and packaging assets
- `docs/` — design, operational and implementation documentation
- `hardware/` — hardware-specific notes
- `artifacts/` — local generated outputs; inventory contents are ignored

## Development

Requirements: Python 3.11+, GNU Make and a virtual environment.

```bash
make venv
make install-dev
make test
make lint
```

Run the API locally only when required:

```bash
make run
curl http://127.0.0.1:8000/api/v1/health
```

## Remote Assist

Open **Remote Assist** to configure one office/customer WireGuard profile and
turn the connection on or off. A computer connected to the same VPN can access
the appliance using its VPN address. The UI reports a recent handshake as
Connected and shows the configured address separately from connection state.

Ethernet is the preferred uplink. USB phone WAN is the fallback when the
Ethernet default route disappears; internet-health-based failover is not yet
implemented. Generic USB-RJ45 WAN adapter support has not been qualified in this
version. The Service port retains its Recovery role.

See [Remote Assist](docs/remote-assist.md), [USB WAN setup and tests](docs/usb-wan.md)
and [network design](docs/network-design.md).

## Appliance installation

On a prepared ARM64 host:

```bash
sudo ./scripts/bootstrap.sh
sudo ./scripts/install-dependencies.sh
sudo ./scripts/install-containers.sh
```

For USB phone WAN and Remote Assist, install their host modules explicitly:

```bash
cd /opt/kronoskvm
sudo bash scripts/install-usb-wan.sh
sudo bash scripts/install-remote-assist.sh
```

These commands are not a complete unattended OS-image installer. Boot overlays,
management/recovery networking, HTTPS certificate provisioning and physical
port mapping must be prepared and verified. See [base OS preparation](docs/base-os.md).
Each new appliance needs its own WireGuard private key, server peer entry and
VPN IP; do not clone an existing device's VPN identity.

The permanent management AP and Ethernet path must be verified before changing
network configuration. Normal deployment must not remove both management paths
in one transaction.

## Access

The local management interface is available at:

```text
https://192.168.34.100
```

Ethernet access uses the DHCP address assigned by the connected network. The
management AP SSID for the current prototype is `KronosDX-iKVM` and is open
during development. HTTPS uses the appliance certificate; trust/hostname handling
must be configured for each installation. Production builds still require user
authentication and an approved wireless security policy.

## Security notes

- Never commit passwords, private keys, Wi-Fi secrets or customer data.
- Do not expose the management UI to untrusted networks without authentication
  and HTTPS.
- Do not enable arbitrary command execution through API routes.
- Keep host power control limited to the allow-listed `reboot` and `poweroff`
  actions.
- Keep USB virtual media read-only by default.

See [SECURITY.md](SECURITY.md) and [docs/security.md](docs/security.md).

## Current limitations

- RTC/power-control board is not installed.
- HTTPS is implemented; per-user web authentication is not.
- Video recording remains unresolved; do not treat it as validated.
- A clean-OS installation on a second appliance is the next reproducibility check.
- Remote Assist currently supports one private-IPv4 peer profile; public web
  access, multiple customer profiles and automatic WAN health failover are pending.
- Power-off cannot restart the GPIO-powered prototype without cycling power.
- Final USB VBUS isolation and enclosure wiring remain hardware milestones.

## License

Copyright belongs to KronosDX. Redistribution is not currently authorized; see
[LICENSE](LICENSE) and [docs/decisions.md](docs/decisions.md).
