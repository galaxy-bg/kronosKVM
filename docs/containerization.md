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

Image builds use host networking only while resolving and downloading build
dependencies. The running API still has all capabilities dropped, a read-only
root filesystem and no Docker socket.

## Deployed baseline

The ARM64 API container is deployed on the CM4 and managed by
`kronoskvm-containers.service`. The native API unit is installed but disabled
for rollback. The deployment has been verified across a reboot with:

- the API healthy on `127.0.0.1:8000`;
- the container running as UID/GID `10001`;
- read-only CM4 device-tree and system visibility;
- no `docker0` bridge or Docker NAT rules;
- IPv4 forwarding remaining disabled;
- hostapd and dnsmasq remaining active independently.
