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
- no mandatory device node that can prevent boot when optional hardware is absent;
- a single writable bind mount limited to `/var/lib/kronoskvm/storage` for
  staged operator files;
- read-only `/sys` and `/etc/kronoskvm` mounts.

## Host hardware plane

These remain host-managed:

- hostapd, dnsmasq and customer/AP networking;
- USB gadget/ConfigFS and virtual media;
- GPIO/ATX control;
- boot and device-tree configuration;
- privileged hardware helpers.

Serial and capture will use dedicated host-side brokers or narrowly scoped
containers with explicit `/dev/tty*` or `/dev/video*` access. Optional hardware
must not be a boot dependency and these services must not receive
`privileged: true`.

## Lifecycle

`kronoskvm-containers.service` manages Compose at boot. The native
`kronoskvm-api.service` remains installed but disabled as a rollback path.
The unit intentionally does not pin `KRONOSKVM_VERSION`; development boots use
the Compose default (`dev`) and release deployments may supply an environment
value explicitly.

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

## Development web gateway

The `kronoskvm-web` container serves the initial dashboard and proxies `/api/`
to the localhost API. Nginx listens specifically on `192.168.34.100:80`; port
80 is not open on ETH0.

The container has a read-only root filesystem, drops all capabilities and adds
back only those required to bind port 80, prepare temporary directories and
drop worker privileges. HTTPS and authentication are required before any
customer-network exposure.
