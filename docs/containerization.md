# Containerization

KronosKVM uses a hybrid container architecture.

## Containerized application plane

- FastAPI coordination and health API
- Future web UI and authentication
- Future monitoring and non-privileged session services

The API image is ARM64 compatible and uses:

- a multi-stage Python build;
- a non-root UID/GID;
- read-only root filesystem;
- all Linux capabilities dropped;
- `no-new-privileges`;
- localhost-only port 8000 through host networking;
- no Docker socket;
- no broad `/dev` mount;
- read-only `/sys` and `/etc/kronoskvm` mounts.

## Host hardware plane

These remain host-managed:

- hostapd, dnsmasq and customer/AP networking;
- USB gadget/ConfigFS and virtual media;
- GPIO/ATX control;
- boot and device-tree configuration;
- privileged hardware helpers.

Serial and capture may later use dedicated containers with only explicit
`/dev/tty*` or `/dev/video*` mappings. They must not receive `privileged: true`.

## Lifecycle

`kronoskvm-containers.service` manages Compose at boot. The native
`kronoskvm-api.service` remains installed but disabled as a rollback path.

Rollback:

```bash
sudo ./scripts/rollback-containers.sh
```

The management AP and SSH are independent of application containers.

Docker is configured without its default bridge, iptables management, IP
forwarding or masquerading. KronosKVM containers currently use host networking
only, so Docker must not alter the isolated AP/customer-network policy.
