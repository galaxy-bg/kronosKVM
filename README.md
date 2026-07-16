# KronosKVM

**Prototype / Active Development**

KronosKVM is a portable IP-KVM, virtual-media and infrastructure-access
appliance developed by KronosDX. It targets a Raspberry Pi Compute Module 4
carrier board and combines remote console, USB HID, virtual media, dual-network
connectivity, serial-console management and local field-service operation.

> HDMI capture, USB HID and virtual media are not active yet. Hardware mappings
> are provisional until verified. Do not expose development services to
> untrusted networks.

## Current scope

The repository currently contains the Milestone 0 project foundation and the
read-only discovery tooling for Milestone 1. All optional hardware modules must
report their state without preventing the API from starting.

Planned module states are `ready`, `running`, `disabled`, `not_detected`,
`waiting_for_hardware`, `unsupported` and `error`.

## Planned capabilities

- HDMI-to-CSI remote console capture and low-latency streaming
- USB keyboard, mouse and virtual-media gadget functions
- Multiple serial-console sessions
- Dual Ethernet and optional Wi-Fi client/access-point modes
- Local touchscreen operation
- System health, secure HTTPS management and future KDX Genesis integration

## Confirmed platform

- Raspberry Pi Compute Module 4 Rev 1.1, 4 GB RAM, aarch64
- Carrier marking: `CM4-DUAL-ETH-WIFI6-BASE`
- Debian GNU/Linux 11 (Bullseye), Linux `6.1.21-v8+`
- Dual Ethernet, three USB host ports and a USB-C port labelled `SLAVE`
- CAM0/CAM1, DSI display, RTC battery, fan and provisional M.2 positions

The current management path is Wi-Fi (`wlan0`) at `192.168.31.145`. Both
Ethernet interfaces had no carrier during the first inventory. The operating
system is older than the intended production baseline and will be reviewed in a
later milestone rather than upgraded in place.

HDMI0 and HDMI1 appear to be local display outputs. Target HDMI input is
expected to use a future HDMI-to-CSI module on CAM0. Exact electrical functions
remain unverified.

## Provisional physical mapping

| Chassis port | Proposed role | Status |
|---|---|---|
| ETH0 | Primary management | Unverified |
| ETH1 | Isolated target/service network | Linux `eth1` is USB RTL8152; chassis mapping unverified |
| USB1 / USB2 | Serial adapters | Unverified |
| USB3 | Expansion/maintenance | Unverified |
| USB-C SLAVE | USB HID and virtual media | No UDC currently registered |
| CAM0 | Primary HDMI-to-CSI capture | Waiting for hardware |
| CAM1 | Future second capture | Waiting for hardware |
| DISP | Local touchscreen | Unverified |

See [physical port map](docs/physical-port-map.md) and
[hardware notes](docs/hardware.md).

## Architecture

The initial control plane uses Python, FastAPI and Pydantic. Production services
will be separated into API, web, capture, HID, virtual-media, serial, network,
display and health components. Development API binding is
`127.0.0.1:8000`; only SSH should be remotely reachable in the initial phase.

See [architecture](docs/architecture.md) and [port plan](docs/port-plan.md).
Base OS preparation is documented in [docs/base-os.md](docs/base-os.md).
OS update policy is documented in [docs/os-migration.md](docs/os-migration.md).
The read-only API is documented in [docs/api.md](docs/api.md).

## Repository overview

- `backend/` — typed FastAPI control-plane skeleton
- `frontend/` — future browser UI
- `config/` — inactive configuration examples
- `scripts/` — safe bootstrap, inventory and future configuration entry points
- `docs/` — architecture, hardware, network, security and implementation notes
- `hardware/` — hardware-specific design material
- `deploy/` — future systemd, Nginx and packaging assets
- `artifacts/` — local generated outputs; inventory contents are ignored

## Development

Requirements: Python 3.11+, GNU Make and a virtual environment.

```bash
make venv
make install-dev
make test
make lint
```

Run locally only when explicitly needed:

```bash
make run
curl http://127.0.0.1:8000/api/v1/health
```

## Initial installation workflow

1. Complete read-only inventory and verify the carrier-board topology.
2. Review `/etc/kronoskvm`, `/var/lib/kronoskvm` and service-account plans.
3. Install dependencies only after explicit approval.
4. Keep capture, HID, virtual media, serial TCP and routing disabled.
5. Add systemd and Nginx only in their later milestones.

No production installation or service activation is performed in Milestone 0.

## Secure SSH workflow

The initial target is `kronosdx@192.168.31.145`, with local alias `kronoskvm`.
Password authentication is used only interactively to install a public key.
Passwords and private keys must never enter this repository, scripts, logs or
command arguments. Password login remains enabled during the discovery phase.

## Hardware discovery

```bash
./scripts/inventory.sh
./scripts/remote-inventory.sh kronoskvm
```

Inventory is read-only and saved below `artifacts/inventory/`, which is excluded
from Git. It does not collect password hashes, private keys, shell history,
tokens, Wi-Fi secrets or environment variables.

## Security warnings

- Never bind development APIs to non-loopback addresses.
- Do not enable forwarding, NAT, bridges, DHCP or Wi-Fi AP mode initially.
- Do not enable USB gadget mode before the correct UDC is verified.
- Never expose VNC, serial TCP, metrics or video streams publicly by default.
- API routes must not provide arbitrary shell execution.

See [security policy](SECURITY.md) and [security design](docs/security.md).

## Roadmap and limitations

Milestones are documented in [development plan](docs/development-plan.md).
The current prototype has a localhost-only health API and serial discovery/lock
foundation. It has no active capture, HID, virtual media, serial data transport,
authentication, HTTPS or production web UI.

## Photo gallery

Physical photos are intentionally not committed yet. Expected filenames and
safe descriptions are documented in [docs/images/README.md](docs/images/README.md).
Once supplied, the front, rear and internal views will be added here.

## License

Copyright belongs to KronosDX. Redistribution is not currently authorized; see
[LICENSE](LICENSE). This temporary decision is recorded in
[docs/decisions.md](docs/decisions.md).
