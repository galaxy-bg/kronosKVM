# KronosKVM

**Prototype / Active Development**

KronosKVM is a portable, browser-managed IP-KVM and infrastructure-access
appliance developed by KronosDX. The current prototype combines HDMI capture,
USB keyboard and mouse emulation, two serial-console ports, staging storage,
network connections, session logging and a permanent local management access
point.

Product descriptor: **All-in-One IP-KVM System**.

> This is a development appliance. Authentication and HTTPS are still required
> before deployment on an untrusted or production network.

## Current prototype

- Raspberry Pi 4 Model B Rev 1.5, aarch64
- 64 GB microSD; 32 GiB logical internal staging pool
- Geekworm X630 HDMI-to-CSI bridge on CSI-2
- USB-C DWC2 controller in peripheral/device mode for KVM OTG
- Two black USB-A 2.0 ports assigned to Console 1 and Console 2
- Two blue USB-A 3.0 ports assigned to Service USB and External Storage
- Native Ethernet for customer/development access
- Integrated Wi-Fi management AP at `192.168.34.100/24`
- Debian GNU/Linux 13 with Raspberry Pi kernel `6.18.34+rpt-rpi-v8`
- GPIO 5V prototype power; RTC/power-control board pending

The current Ethernet DHCP address is installation-specific. The development
prototype was last verified at `192.168.31.185`.

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

Virtual-media file staging is active. Presenting an ISO or image to the target
as a USB mass-storage gadget remains a later milestone.

## Physical port assignment

| Physical port | Appliance role | Verified topology |
|---|---|---|
| Black USB-A 2.0 #1 | Console 1 | `1-1.3` |
| Black USB-A 2.0 #2 | Console 2 | `1-1.4` |
| Blue USB-A 3.0 #1 | Service USB / optional USB Ethernet | USB 2 companion `1-1.1`, SuperSpeed `2-1` |
| Blue USB-A 3.0 #2 | External Storage | USB 2 companion `1-1.2`, SuperSpeed `2-2` |
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

KronosKVM uses a hybrid host/container architecture:

- `kronoskvm-api`: FastAPI control plane, KVM/serial sessions, logs and storage
- `kronoskvm-web`: Nginx-hosted browser UI and reverse proxy
- host systemd helpers: capture initialization, ConfigFS USB gadget, power
  actions, networking and container lifecycle
- hostapd/dnsmasq: isolated Wi-Fi management AP

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

## Appliance installation

On a prepared ARM64 host:

```bash
sudo ./scripts/bootstrap.sh
sudo ./scripts/install-dependencies.sh
sudo ./scripts/install-containers.sh
```

The permanent management AP and Ethernet path must be verified before changing
network configuration. Normal deployment must not remove both management paths
in one transaction.

## Access

The local management interface is available at:

```text
http://192.168.34.100
```

Ethernet access uses the DHCP address assigned by the connected network. The
management AP SSID for the current prototype is `KronosDX-iKVM` and is open
during development. Production builds require authentication, HTTPS and an
approved wireless security policy.

## Security notes

- Never commit passwords, private keys, Wi-Fi secrets or customer data.
- Do not expose the management UI to untrusted networks without authentication
  and HTTPS.
- Do not enable arbitrary command execution through API routes.
- Keep host power control limited to the allow-listed `reboot` and `poweroff`
  actions.
- Keep USB mass storage read-only by default when virtual media is implemented.

See [SECURITY.md](SECURITY.md) and [docs/security.md](docs/security.md).

## Current limitations

- RTC/power-control board is not installed.
- USB virtual-media attachment is not implemented; staging is available.
- HTTPS and user authentication are not implemented.
- Power-off cannot restart the GPIO-powered prototype without cycling power.
- Final USB VBUS isolation and enclosure wiring remain hardware milestones.

## License

Copyright belongs to KronosDX. Redistribution is not currently authorized; see
[LICENSE](LICENSE) and [docs/decisions.md](docs/decisions.md).
