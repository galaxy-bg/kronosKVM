# Architecture

KronosKVM is an independent modular appliance. PiKVM is a technical reference,
not a source-tree template.

Planned services:

- `kronoskvm-api`: coordination and versioned API
- `kronoskvm-web`: browser interface
- `kronoskvm-capture`: HDMI-to-CSI capture and streaming
- `kronoskvm-hid`: keyboard and mouse gadget control
- `kronoskvm-virtual-media`: read-only-first image attachment
- `kronoskvm-serial`: serial discovery and locked sessions
- `kronoskvm-network`: explicit network-mode management
- `kronoskvm-display`: optional local touchscreen
- `kronoskvm-health`: device and service monitoring

Hardware adapters are optional and expose explicit state. Missing hardware must
not stop the control plane. Privileged operations will live behind narrow,
audited helpers rather than arbitrary command execution.

The Milestone 3 API runs as `kronoskvm` through systemd and listens only on
`127.0.0.1:8000`. It reads system state but exposes no mutation endpoints.

## Hybrid container model

The application plane runs through Docker Compose while network and privileged
hardware helpers remain host systemd services. The native API service is kept
as rollback. See [containerization](containerization.md).

The development web gateway runs as a hardened Nginx container. It binds only
to `192.168.34.100:80` on the isolated AP, serves static frontend assets and
proxies same-origin `/api/` requests to `127.0.0.1:8000`. It does not listen on
the ETH0 DHCP address.
