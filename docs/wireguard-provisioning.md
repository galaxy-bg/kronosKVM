# WireGuard provisioning and Settings integration

Operator guide (Türkçe): [Sıfırdan kurulum, kayıt ve özelleştirme](wireguard-kullanim-kilavuzu.md).

## Architecture and implementation plan

The existing appliance uses FastAPI, a static JavaScript web UI, single-admin
session authentication, a root systemd host helper, and NetworkManager owning
`wg-kdx`. Reuse these boundaries: the API queues validated actions; systemd runs
the host helper under its existing file lock; only the root helper sees keys.
The existing Remote Assist page and LCD controls continue to operate on the same
profile. Settings adds provisioning controls rather than a separate application.

The implementation supports manual registration and Generate & Register using
an administrator-issued, device-bound, short-lived SSH forced-command grant.
No public provisioning API or server password is installed on the InfraBox.
A request UUID is correlation, not a credential; the restricted SSH key and
server grant authorize one device registration. Connect remains a separate action.

## Read-only infrastructure inspection — 2026-10-15

- `172.12.2.74`: Rocky Linux 9.5, active `wg0`, `10.77.0.1/24`, UDP 51820.
- Existing live peers use `10.77.0.2/32` and `10.77.0.10/32`.
- Existing `wg0.conf` has those peers and no `SaveConfig=true` directive.
- `192.168.31.26`: `infrabox-000865dd`, serial `10000000000865dd`, `wg` installed,
  no `wg-kdx` interface, no existing controller keyfile or recovery `.conf`.
  Server address routes through Ethernet via `192.168.31.1`.
- The other previously known appliance at `192.168.31.185` timed out on SSH;
  rediscover its address before scheduling its deployment.

At this initial inspection stage, no production configuration was changed.
The subsequent user-approved deployment and live verification are recorded below.
Production VPN connection testing received a separate explicit user approval.

## Files

| File | Responsibility |
| --- | --- |
| `scripts/kdx-wg-server.sh`, `scripts/kdx-wg-server.py` | Locked local Rocky server peer management |
| `scripts/remote-assist-host.py` | Local key generation, approved registration, recovery config, transactional client actions, startup restoration |
| `scripts/infrabox-wireguard.py` | Root CLI over the same client controller |
| `scripts/install-wireguard-provisioning.sh` | Host integration using existing systemd units |
| `backend/app/services/wireguard_provisioning.py` | Strict public enrollment protocol |
| `backend/app/api/wireguard.py` | Settings provisioning/status endpoints |
| `backend/app/api/remote_assist.py`, `backend/app/security/auth.py` | Explicit admin policy, including legacy mutation routes; preserve scoped LCD actions |
| `backend/app/main.py` | Register API router |
| `frontend/src/wireguard.js`, `frontend/src/wireguard.css` | Settings UI and responsive layout |
| `frontend/src/index.html`, `frontend/src/auth.js` | Mount/load the section in the existing UI |
| `backend/tests/test_wireguard_server.py`, `backend/tests/test_wireguard_provisioning.py`, `backend/tests/test_auth.py` | Failure, validation, privacy and authorization tests |

Existing Remote Assist business tests now isolate host files under temporary
paths. The business-test authentication bypass also supplies an admin session;
`test_auth.py` exercises the actual middleware and admin guard.

## Ownership, secrets and networking

New identities use `wg genkey` locally and pass the private key to `wg pubkey`
through stdin. It never enters the enrollment protocol, GUI responses, shell
arguments or logs. Root-only identity/configuration/backups remain on the box.
The public request contains only version, hardware device ID, hostname, public
key and request UUID. Import must match all five fields and the current board,
and the stored key pair is checked before profile installation. Generating an
identity is idempotent and does not rotate an existing imported profile.

The controller also generates `/etc/wireguard/wg-kdx.conf`, mode 0600, as a
recovery artifact. **NetworkManager remains the sole interface owner.** Do not
enable `wg-quick@wg-kdx`; registration and installation reject an active competing
wg-quick service. The existing systemd action/path/status/boot units manage the
lifecycle. Startup preference is restored even after an explicit disconnect in
the previous session. Disconnect preserves the profile and startup preference.

The default peer route is `10.77.0.0/24`. Client address is installed as `/32`;
never-default, ignore-auto-DNS and disabled automatic default-route flags are
retained. Full tunnels, IPv6, LAN/recovery/USB subnet overlap, endpoint-in-tunnel,
DNS overrides and imported shell hooks are rejected. No command enables NAT,
customer LAN forwarding, IP forwarding or customer access automatically.
Existing AP access policy is a separate setting and remains unchanged.

There is currently no Operator account or general RBAC user management in this
repository. The existing admin policy is enforced for all new and legacy VPN
mutations; a non-admin/Operator session can read status but is denied writes.
The UI mirrors that rule. Tests exercise a future read-only role explicitly;
this feature does not add or claim a complete multi-user account system.

## Approved installation

Do this only after approving the reviewed changes. Copy the reviewed application
source to `/opt/kronoskvm` while preserving existing device configuration and
state. Back up application source, `/etc/kronoskvm`, NetworkManager keyfiles,
`/etc/wireguard` if present, and current API/web image tags to a root-only location.
Use the existing container build/reload process for the API and web changes:

```bash
cd /opt/kronoskvm
sudo bash scripts/install-wireguard-provisioning.sh
sudo docker tag kronoskvm-api:dev kronoskvm-api:pre-wg-provisioning
sudo docker tag kronoskvm-web:dev kronoskvm-web:pre-wg-provisioning
sudo docker-compose build api web
sudo systemctl reload kronoskvm-containers.service
```

The host installer enables existing action/status services; it does not create
an identity or change the selected VPN profile or connection state. It requires
NetworkManager and rejects a competing active wg-quick owner. It installs
wireguard-tools through the existing installer if missing.

Install the server scripts together so the wrapper resolves its Python helper:

```bash
sudo install -m 0755 scripts/kdx-wg-server.sh /usr/local/sbin/kdx-wg-server.sh
sudo install -m 0755 scripts/kdx-wg-server.py /usr/local/sbin/kdx-wg-server.py
```

These scripts use the server's Python 3 standard library and `wg`; no new server
service, listening port, firewall rule or tunnel restart is required.

## Manual approval and enrollment

In **Settings → WireGuard VPN**, choose Create device identity, then Download
registration request. Send that public JSON to the administrator over the
approved administrative channel. The equivalent appliance CLI is:

```bash
cd /opt/kronoskvm
sudo python3 scripts/infrabox-wireguard.py identity
sudo python3 scripts/infrabox-wireguard.py request > infrabox-registration.json
```

On the VPN server, inspect the public request and verify its serial/name against
the physical device inventory. Approval is a deliberate local root command:

```bash
sudo /usr/local/sbin/kdx-wg-server.sh add \
  --request /root/infrabox-registration.json \
  --endpoint 172.12.2.74:51820 > approved-registration.json
```

Verify that the endpoint is reachable from the device's intended deployment
network; use the approved public hostname/address if it differs from the server's
management IP. IP allocation defaults to `.11` through `.254`; the allocator
excludes network/broadcast, interface addresses, registry assignments, and every
file/live peer AllowedIPs range. Optional `--ip` is subject to the same checks.
`--network`, `--pool-start` and `--pool-end` configure a private IPv4 pool.
Duplicate names, device IDs, request UUIDs, public keys and assigned IPs fail.

Import the approved public JSON in Settings, or enter the approved assigned IP,
server endpoint, server public key and routes manually. Import does not connect
or replace an active profile. Disconnect first if replacing an existing profile.
Then choose Connect and, separately, the desired automatic startup preference.
The equivalent appliance CLI is:

```bash
cd /opt/kronoskvm
sudo python3 scripts/infrabox-wireguard.py import approved-registration.json
sudo python3 scripts/infrabox-wireguard.py connect
sudo python3 scripts/infrabox-wireguard.py boot-on
sudo python3 scripts/infrabox-wireguard.py status
# Other explicit actions: disconnect, restart, boot-off
```

Inspect a recent handshake and reachability from an authorized VPN peer before
calling deployment successful. Interface creation or an accepted request alone
is not evidence of a handshake. The GUI reports waiting_handshake distinctly.

## Server management and failure behavior

```bash
sudo /usr/local/sbin/kdx-wg-server.sh list
sudo /usr/local/sbin/kdx-wg-server.sh status
sudo /usr/local/sbin/kdx-wg-server.sh export infrabox-000865dd > approved-registration.json
sudo /usr/local/sbin/kdx-wg-server.sh remove infrabox-000865dd
```

`list`/`export` operate on registered managed peers. `status` includes live peers,
including pre-existing unmanaged ones. Remove refuses unmanaged peers or a peer
whose assigned routes were edited outside provisioning. A file lock serializes
all operations. Each modification backs up server configuration and registry
under `/etc/wireguard/kdx-backups/peer-*`, root-only. Peer updates use targeted
`wg set`; they do not replace the interface configuration or restart `wg0`.
On failure, file/registry changes and the targeted live peer are restored; a
rollback failure identifies the root-only backup for operator recovery.

`SaveConfig=true` **refuses mutations**: wg-quick can overwrite file changes on
shutdown. Reconcile live peers with disk, back up both locally with mode 0600,
and explicitly approve switching SaveConfig to false before provisioning.
Do not blindly disable it or restart the tunnel. Existing server hooks and
unmanaged peer blocks are retained verbatim.

Reference: [WireGuard key generation](https://www.wireguard.com/quickstart/),
[wg targeted peer configuration](https://git.zx2c4.com/wireguard-tools/about/src/man/wg.8),
and [wg-quick SaveConfig behavior](https://git.zx2c4.com/wireguard-tools/about/src/man/wg-quick.8).

## Rollback

Client operations create private backups under
`/etc/kronoskvm/remote-assist/backups/provision-*`. Failed operations restore the
previous profile files and previous tunnel state. To roll back a deployment,
stop the action path and status timer, restore the previous host/API/web source
and image tags, restore only the intended prior profile/keyfile/recovery config
from the matching backup, reload NetworkManager's specific profile and the
container service, then restore previously enabled units. Do not restore all
private device state or unrelated network configuration indiscriminately.

To revoke an enrolled device use the server tool's `remove`; this removes only
that device and creates another backup. It does not roll back application code.
If automatic server rollback failed, use the recorded root-only `interface.conf`,
`registry.json` and `live-peer.conf` to reconcile only the affected peer; never
publish those files or restart all VPN tunnels as a recovery shortcut.

Keep client identity files in place when rolling back GUI code if that identity
is already registered; deleting it makes that public registration unusable.
All key-containing backups must stay root-only on the device/server.

## Validation and limits

Tests cover mocked key generation and systemd/NetworkManager/WireGuard commands,
public-only request/response schemas, mismatched and corrupted device identities,
CIDR/route constraints, secret-safe API failures, request locking, pool exhaustion,
SaveConfig protection, peer preservation, and rollback after simulated failures.
Real Chrome exercised the Settings identity/public registration/connect/disconnect/
automatic startup and read-only role controls with mocked API responses and no
page errors. The real app stylesheet and DOM were used; the host networking was
not changed for browser testing. A screenshot is available in the review artifacts.

The approved deployment below verifies registration, handshake and management
reachability. Full OS reboot persistence and qualification of another box remain
unperformed. The unreachable second box remains unmodified.


Reproduce validation from the repository root:

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
bash -n scripts/kdx-wg-server.sh scripts/install-wireguard-provisioning.sh
node --check frontend/src/wireguard.js
npm install --prefix /tmp/kdx-wg-ui-tests --no-audit --no-fund playwright-core
NODE_PATH=/tmp/kdx-wg-ui-tests/node_modules node tests/browser/wireguard.cjs
```

The manual provisioning stage passed **252 tests**. The final automatic enrollment
implementation passed **260 tests**. Browser assertions cover the
same-device public registration and controls with mocked API responses; they do
not claim a real server handshake. The review screenshot is
`artifacts/wireguard-provisioning/settings-preview.png`. The prepared source
archive and SHA256 are in the same artifact directory; no private device state
or credentials are included. This repository already contained unrelated local
LCD and production-display changes; those were retained, not reverted or committed.


## Automatic registration with a one-time grant

Settings → **Generate & Register** generates the WireGuard identity locally,
invokes the server enrollment script through pinned SSH, validates the returned
public metadata and installs it. The operator does not handle WireGuard private
keys or copy registration files. Manual identity/download/import remains available.
The action does not automatically connect the VPN.

A trusted administrator prepares a limited grant once per device. Install
`scripts/kdx-wg-enroll.py` alongside both server management scripts under
`/usr/local/sbin/`. Read `/etc/ssh/ssh_host_ed25519_key.pub` over the existing
trusted administrative connection; deliver only this public key to the box.
Do not replace host-key verification with an unverified ssh-keyscan result.

On the InfraBox:

```bash
cd /opt/kronoskvm
sudo python3 scripts/configure-auto-enrollment.py prepare \
  --host 172.12.2.74 --host-key-file /tmp/approved-server-host-key.pub \
  > enrollment-transport.pub
```

Transfer only `enrollment-transport.pub` to the server. It is a separate public
SSH transport key, not the WireGuard key. The private SSH key stays root-only on
the InfraBox. Approve the specific physical device on the server:

```bash
sudo /usr/local/sbin/kdx-wg-enroll.py authorize \
  --device-id 10000000000865dd --hostname infrabox-000865dd \
  --ssh-public-key-file /root/enrollment-transport.pub \
  --endpoint 172.12.2.74:51820 --ttl 900 > approved-enrollment-grant.json
```

Deliver that public grant JSON through the administrative channel to the box:

```bash
cd /opt/kronoskvm
sudo python3 scripts/configure-auto-enrollment.py authorize \
  --grant /tmp/approved-enrollment-grant.json
# Then click Generate & Register, or use the same controller from the CLI:
sudo python3 scripts/infrabox-wireguard.py auto-register
```

The existing SSH daemon accepts the key only with `restrict`, a UTC
`expiry-time`, and the fixed enrollment forced command. No shell, PTY, agent,
port forwarding or arbitrary server command is permitted. Grant records are
root-only under `/var/lib/kdx-wg-enrollment`. Default lifetime is 15 minutes;
permitted lifetime is 1–30 minutes. The grant is bound to the approved serial
and hostname, and becomes bound to one exact public request on first use.
Server and appliance clocks must agree.

Only one peer is created per grant. If the authenticated public response is lost,
retrying the identical request retrieves that response without provisioning a
second peer. Another key/request is rejected. The box saves a validated public
reply before installing the profile, so an interrupted local installation can
recover even after the SSH grant expires. Generation and registration errors
never print SSH/WireGuard private keys or subprocess stderr.

Revoke an enrollment grant (this does not revoke an already-created VPN peer):

```bash
sudo /usr/local/sbin/kdx-wg-enroll.py revoke --lease GRANT_UUID
```

Revocation removes only that restricted authorized-key entry and preserves all
existing administrative SSH keys. Before reauthorizing the same transport key,
revoke its prior grant. To revoke VPN access, separately use `kdx-wg-server.sh
remove DEVICE_NAME`. The server's ordinary SSH authentication configuration is
not changed. Expired entries cannot authenticate, even if not yet removed.

The new authenticated endpoint is `POST /api/v1/wireguard/enroll`. Only existing
admin sessions may call it. The existing systemd action service has a 240-second
budget for the bounded SSH operation and rollback; the GUI waits for its correlated
result. LCD/legacy connection controls continue to use the same profile.

Reference: [OpenSSH authorized_keys forced commands, restrict and expiry-time](https://man.openbsd.org/sshd.8#AUTHORIZED_KEYS_FILE_FORMAT).


## Approved live deployment — 2026-10-15

Installed the reviewed source on `192.168.31.26` (`infrabox-000865dd`) and the three
server scripts on `172.12.2.74`. User approval explicitly covered automatic
registration; a subsequent explicit approval covered connecting for the live
handshake test and disconnecting afterward.

- Client backup: `/var/backups/kronoskvm/pre-wg-auto-20261015.xyXBX3`.
- Server backup: `/var/backups/kdx-wg-auto-20261015.QdEFqk`.
- Previous API/web images: `pre-wg-auto-20261015`; new tags:
  `wg-auto-20261015`, also `dev`.
- ARM64 API import/routes and live nginx validation passed.
- Existing `wg0` service has remained active since September 24; no tunnel restart.
- Existing `.2` and `.10` peers were preserved. The new registered device is
  `10.77.0.11/32`, public WireGuard endpoint `185.251.66.26:51820`, routes
  `10.77.0.0/24`.

### Forti and the enrollment path

The administration workstation reaches `172.12.2.74` through its existing VPN
(`utun5`); the InfraBox's ordinary Ethernet uplink cannot reach server TCP 22.
TCP 22 on the observed public egress IP also timed out. No Forti rule or public
SSH exposure was added. Initial enrollment used this temporary administration
relay, bound only to the box's localhost:

```bash
# Run on the trusted administration workstation with its existing VPN connected.
ssh -N -T -o ExitOnForwardFailure=yes \
  -R 127.0.0.1:45222:172.12.2.74:22 kronosdx@192.168.31.26
# On the box, prepare the same pinned end-to-end SSH transport through this relay.
cd /opt/kronoskvm
sudo python3 scripts/configure-auto-enrollment.py prepare \
  --host 127.0.0.1 --port 45222 \
  --host-key-file /tmp/approved-server-host-key.pub
```

Issue/activate the device-bound grant as above. SSH still verifies the real VPN
server host key through the relay. Only public requests/replies traverse it;
WireGuard and enrollment SSH private keys stay on the box. After successful
Generate & Register, revoke the enrollment grant and stop the administration
relay. Both cleanup steps were completed for this deployment. The grant entry
was removed; previous SSH authorization was preserved. The resulting empty
root authorized_keys file was left in place rather than deleting it.

New boxes therefore need either an approved reachable SSH enrollment path or
this temporary trusted administration relay, plus their own short-lived grant.
The GUI does not silently bypass Forti or retain a general-purpose server login.

### Live verification

Real HTTPS Chrome administrator sessions verified the new Settings controls,
then submitted **Generate & Register**. It created the local key pair, invoked
the server script, received `.11`, installed the profile and showed completed
registration without enabling the VPN. Diagnostic sessions were logged out.

A live connection was then present and, after explicit approval, verified:

- Actual current handshake on both ends for the new public key.
- Two-way ICMP: server `.1` ↔ device `.11`, no packet loss.
- Server reached `https://10.77.0.11/api/v1/health` with HTTP 200.
- Anonymous management through the VPN still returned HTTP 401.
- Only the approved `10.77.0.0/24` route was added; the default remained
  `192.168.31.1` via Ethernet.

The test ended with an authenticated GUI/API Disconnect and logout. Final status
is `off`, `enabled=false`, with no `wg-kdx` interface. The registered peer/profile
remains available for the next Connect. The pre-existing automatic startup
preference remains **true**; Disconnect did not change it. No OS reboot was done.

Client routes match the pre-deployment baseline again. Client/server firewall
policies and server routes are unchanged (ignoring packet counters). Existing
TLS, admin authentication state and all pre-existing NetworkManager profiles
match the private backup byte-for-byte. API, web, guacd, LCD and container service
are healthy; systemd reports no failed units. Private identity, SSH key and
recovery `.conf` are root-owned mode 0600.

Final validation: **260 tests**, lint, shell syntax, JS syntax, mocked real-Chrome
manual/automatic enrollment flows, plus actual deployed HTTPS registration and
VPN handshake/reachability checks. Live review screenshots are under
`artifacts/wireguard-provisioning/`.
