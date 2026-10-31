# InfraBox physical device registration agent

Independent host service; it does not replace the existing KVM containers, VPN
identity, Wi-Fi naming or appliance credentials. It reports license authorization;
this phase does not disable or gate existing KVM functions.

Runtime: Python 3.9+ and the OS `python3-cryptography` package. The application
creates its own Ed25519 key and UUID under `/var/lib/kdx-registration` (0700), owned
by dedicated non-login service user `kdx-registration`. Private identity/cache files
are 0600. The server receives only the public identity and challenge signatures.
The actual Pi serial is read from the OS on each invocation; no serial override is
provided by this physical-device agent.

## Installation

Review existing paths before installation; the installer refuses existing client
source/configuration. Copy this directory to a temporary directory on InfraBox:

```sh
sudo bash deploy/install.sh
sudo install -m 0644 config.example.json /etc/kdx-registration-client/config.json
# Edit server_url and pin the server's real public signing key out of band.
# allow_lab_http=true is only for the isolated lab; use verified HTTPS in production.
sudo -u kdx-registration python3 /opt/kdx-registration-client/client.py identity
sudo -u kdx-registration python3 /opt/kdx-registration-client/client.py sync
```

The first sync idempotently enrolls a PENDING installation, verifies proof possession,
and persists a public status snapshot. It cannot activate itself.

Review that exact serial, UUID and public key using the administrator API. Create
or select the customer/license, then `/approve` the exact binding. No administrator
API token is stored on the appliance. Activate by pasting the one-time token at a
hidden prompt (not in argv or shell history):

```sh
sudo -u kdx-registration python3 /opt/kdx-registration-client/client.py activate
sudo systemctl enable --now kdx-registration-client.timer
sudo systemctl start kdx-registration-client.service
sudo -u kdx-registration python3 /opt/kdx-registration-client/client.py status
```

The timer validates after boot and every five minutes. It locks concurrent local
runs and retains its installation identity over restart. Its status file contains
no private keys, activation tokens or bearer sessions. Authentication responses are
checked against the pinned server signing key and local serial/UUID/key/device ID. Up to 30 seconds of clock skew is allowed
only for the document issue time; expiry is enforced strictly. Keep server/device
NTP synchronized.

## Offline behavior

Only a previously validated signed ACTIVE document grants temporary offline status.
The server defaults to 24 hours, capped by license expiry. Fresh, denied, expired or
hardware-mismatched identities fail closed. A reachable server denial erases local
gracing rights. TLS validation failures and malformed responses do not trigger
offline fallback. Offline revocation, trusted-time and cloned-key limitations remain
as documented in the registration server security guide. Software-only serial
reporting is not hardware attestation.

## Previous lab transport (superseded by verified WAN)

The earlier home-lab setup reached the WireGuard subnet, but its existing VPN
AllowedIPs excludes the `172.12.2.0` lab network. Do not silently change the VPN or
Caddy host to solve this. For supervised enrollment a workstation can provide a
loopback-only reverse SSH tunnel:

```sh
ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 \
  -R 127.0.0.1:13000:172.12.2.82:8080 kronosdx@192.168.31.27
```

While that tunnel runs, use `server_url=http://127.0.0.1:13000` with lab HTTP explicitly
allowed. The workstation relays traffic to the existing Caddy routing. It receives
activation/proof HTTP traffic as part of the trusted lab transport; device private
keys remain on InfraBox. There is no persistent VPN/Caddy modification.

**This tunnel depends on the workstation and does not survive its sleep/reboot.**
A signed cached document can cover a limited outage; it is not a permanent network
solution. For unattended operation, provision an appliance-reachable HTTPS URL or
separately authorize VPN routing. After that change, update only the client's
server_url and validate with the same pinned signing key/identity. Never regenerate
an active identity as a connection-recovery shortcut.

## Golden manufacturing images and recovery

Do not include `/var/lib/kdx-registration` identity/cache or one-time tokens in a
manufacturing master image. A fresh image generates its own UUID/key. Cloning an
already activated SD onto a different Pi must fail binding checks and requires
explicit administrator review. Reinstalling the same Pi with a new UUID/key also
requires recovery; its serial alone never authorizes it. Back up the existing device
identity privately before upgrades, and never publish that backup to GitHub.

## Tests

From repository root, after installing `registration-server/requirements.lock`:

```sh
registration-server/.venv/bin/python -m pytest -q device-registration/tests
```

The tests exercise the actual server protocol and agent together: pending enrollment,
activation, stable identity across restart, private-file permissions, transport-only
offline grace and expiry, clone mismatch, revocation, signing-key mismatch, HTTP lab
opt-in and rejection of unexpected challenge domains. PostgreSQL can be selected
using the server test suite's disposable `KDX_TEST_DATABASE_URL` convention.

## Verified WAN update

The real appliance now uses `https://185.251.66.26:18444`, with explicit lab CA
provisioning, verified CA fingerprint, normal certificate-chain/IP verification and
lab HTTP disabled. The workstation relay was removed. See
[WAN acceptance and commands](docs/WAN-ACCEPTANCE-20261031.md).

The host agent publishes only allowlisted non-secret state under
`/var/lib/kdx-registration-public`, read-only in the API container. The Settings
registration card and `/api/v1/system/registration` do not expose private keys,
activation tokens, sessions or the private signed-document cache.
