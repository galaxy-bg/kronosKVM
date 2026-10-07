# Browser Telnet, RDP and VNC sessions

Saved Telnet, RDP and VNC connections open inside the InfraBox UI. The appliance
connects to the target; the browser does not need a native client or direct
network access to that target. SSH retains its existing browser terminal, and
Web URL profiles retain their existing new-tab behavior.

## Connection flow

1. Save a connection with its name, protocol, host, port and optional username.
2. Open the saved connection. Enter session credentials in the masked form.
   Telnet credentials can be left empty to sign in at the target's terminal
   prompt. VNC uses the target's VNC password.
3. RDP can additionally use a domain and explicit security mode. Certificate
   validation is enabled by default. Select the unverified-certificate option
   only when you intend to trust that target's certificate.
4. Use the in-page terminal/desktop with keyboard, mouse or a touchpad gesture.
   **Ctrl+Alt+Del** sends the key combination to the target. The masked text
   field and **Send ↵** let mobile users send text followed by Enter.
5. Close the window to disconnect. Minimize keeps the session connected.

Passwords are sent in the first authenticated WebSocket body and passed to the
local gateway for that session. They are not stored in connection profiles,
browser storage, URLs or application audit logs. Logout, password changes and
admin-session expiry revoke active remote sockets through the existing
authentication middleware.

## Runtime

The data path is:

```text
Browser → HTTPS/WSS Nginx → authenticated FastAPI → localhost guacd → target
```

The Compose service `kronoskvm-guacd` uses Apache Guacamole 1.6.0, pinned to its
multi-architecture image digest. Its native daemon listens only on
`127.0.0.1:4822` using host networking, matching the appliance's disabled IP
forwarding policy. Do not expose guacd directly: it does not authenticate clients.
The browser client is bundled locally in `frontend/src/vendor`; no runtime CDN,
separate Guacamole login, database or Java application is required.

Container startup starts guacd before the API/web plane. The gateway runs
non-root, with a read-only root filesystem, dropped capabilities and temporary
storage. Four remote sessions are allowed at once. Compose requests 384 MiB and
128-process limits; memory enforcement requires host kernel/cgroup support.
The current prototype reported that memory limits are not supported during the
isolated test, so the requested memory limit must not be treated as enforced.

For an existing installation, install the updated application files, rebuild
the API/web images and reload `kronoskvm-containers.service`. This starts the
new guacd service and reconnects the application containers. Active sessions
are disconnected. Keep backups of the previous application files and image tags
for rollback. `docker-compose build` alone does not start guacd.

The gateway uses the appliance's LAN/VPN routing and DNS. The target still needs
its Telnet/RDP/VNC server enabled and reachable. HTTPS protects the browser-to-box
link; Telnet remains plaintext on the box-to-target link. Clipboard, audio, file
transfer and remote session recording are not enabled in this first version.
VNC servers requiring proprietary authentication may need a compatible RFB
configuration.

## Validation — 2026-10-04

This implementation was deployed to the second appliance at `192.168.1.107`
on 2026-10-04 and the first prototype at `192.168.31.185` on 2026-10-07. See the
[second-appliance update record](second-appliance-update-20261004.md) and
[first-appliance update record](first-appliance-update-20261007.md).

- Local tests exercise framing, UTF-8 fragmentation, guacd argument ordering,
  gateway cleanup, limits, invalid profiles, TLS defaults and authenticated
  WebSocket access/revocation.
- Real Chrome at 1400px and 390px verified all three credential forms, rendered
  frames, keyboard/mouse input, close and desktop maximize using a simulated
  WebSocket gateway.
- The real official ARM64 guacd image passed isolated Telnet and VNC tests with
  loopback target fixtures: handshake, rendered output and target input.
- The real ARM64 RDP plugin returned its handshake arguments. Login and desktop
  control against an actual RDP target remain pending. The fixtures do not
  validate a customer's target credentials or protocol settings.
- The isolated test container and fixtures were removed; existing API/web
  containers remained healthy.

Upstream references: [Guacamole protocol](https://guacamole.apache.org/doc/gug/guacamole-protocol.html),
[connection parameters](https://guacamole.apache.org/doc/gug/configuring-guacamole.html),
and [container installation](https://guacamole.apache.org/doc/gug/guacamole-docker.html).
