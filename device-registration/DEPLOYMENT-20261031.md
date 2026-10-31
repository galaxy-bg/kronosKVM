# Physical InfraBox onboarding — 2026-10-31

This initial supervised relay was subsequently replaced by verified WAN HTTPS.
See [WAN acceptance](docs/WAN-ACCEPTANCE-20261031.md) for current transport and reboot results.

Explicitly authorized by the owner: enroll the real appliance, approve it, activate
it with a 30-day DEMO license under KronosDX Lab.

| Field | Value |
| --- | --- |
| Appliance | `infrabox-000865dd`, LAN `192.168.31.27` |
| Hardware serial | `10000000000865DD` |
| Installation UUID | `c96d6174-2e02-4fc7-b065-6d27809d22f2` |
| Public registration key | `xGcqAylcOo3w3ILJdPjqFDgtsC78m6NVvjq6rXcGwKY=` |
| Server device ID | `6998bfa8-3a28-4822-b290-ec1927cfa4b4` |
| Customer | `KronosDX Lab` |
| License | `36833f3a-fe4e-44d8-a956-681063c1bafe`, DEMO, one device |
| License expiry | **2026-11-30 22:19:19 Europe/Istanbul** |
| Final status | `ACTIVE`, `online`, authorized true |

The device first enrolled as PENDING through the existing Caddy route. Its actual
OS hardware serial, generated UUID and public key were checked against the server
record before approval. The administrator token never went to the appliance; only
a short-lived, device-bound activation token was transferred over SSH. That token
was consumed once; temporary copies on the server, workstation and appliance were
removed. The device's private registration key stayed on the appliance throughout.

## Installed files and behavior

- `/opt/kdx-registration-client/client.py`: independent host agent.
- `/etc/kdx-registration-client/config.json`: public URL/signing-key configuration.
- `/var/lib/kdx-registration/identity.json`: persistent private UUID/key, 0600.
- `/var/lib/kdx-registration/authorization.json`: signed authorization/cache, 0600.
- `/var/lib/kdx-registration/status.json`: status snapshot, no tokens or private key.
- `kdx-registration-client.service`: non-root, restricted oneshot unit.
- `kdx-registration-client.timer`: enabled, boot validation and five-minute checks.

The service uses dedicated non-login account `kdx-registration`, private state
0700, and restrictive systemd protections. It does not modify the VPN profile/key,
existing appliance credentials, Wi-Fi naming or KVM container images. Original
`/etc/kronoskvm` file checksums matched after onboarding; API/web/guacd stayed healthy.
No appliance reboot was required or performed. Boot behavior is configured but a
physical reboot was not exercised.

Initial clock diagnostics found the VM approximately 16 seconds ahead of the
NTP-synchronized Pi. The agent now permits at most 30 seconds of future issue-time
skew and enforces document expiry strictly. Ten agent/protocol tests passed, including
that boundary. Chrony was installed and enabled on the Registration VM, which
previously had no time synchronization service; `NTPSynchronized=yes` was verified.
The Rocky installer now includes that prerequisite for future installations.

A real transport-outage check against an unused local port returned ACTIVE in
`offline-grace` mode from the validated signed cache. A subsequent normal systemd
run returned ACTIVE/online. Both hosts showed no failed systemd units afterward.
The server record was independently read through Caddy and confirmed the expected
ACTIVE device/license binding.

## Temporary network path and remaining work

The home appliance can reach VPN `10.77.0.1`, but existing AllowedIPs are limited to
`10.77.0.0/24`. Its route to Caddy `172.12.2.82` uses the home gateway and times out.
No VPN, Caddy or Dashboard configuration was changed.

Current client URL is `http://127.0.0.1:13000`, served by a loopback-only reverse SSH
tunnel from the workstation to the appliance. The workstation forwards to existing
Caddy `172.12.2.82:8080`. The tunnel runs in the background with keepalives and a local
control socket; it depends on the workstation/VPN remaining awake and connected.
It is not installed as a persistent boot service on the workstation.

Check the current relay on the workstation:

```sh
ssh -S /tmp/kdx-registration-lab/relay.sock -O check kronosdx@192.168.31.27
```

When the relay is no longer needed, stop it explicitly:

```sh
ssh -S /tmp/kdx-registration-lab/relay.sock -O exit kronosdx@192.168.31.27
```

After a workstation reboot, the foreground tunnel command in README.md can recreate
the temporary path. For unattended operation, provision an appliance-reachable
HTTPS endpoint or separately approve a VPN routing change. Then update server_url,
retaining the same pinned server key and private identity. Without online validation,
the signed authorization expires after the configured 24-hour grace, even though
the license itself is valid for 30 days. Existing KVM functions are not gated by this
initial registration integration.

Inspect device state:

```sh
sudo -u kdx-registration python3 /opt/kdx-registration-client/client.py status
sudo systemctl start kdx-registration-client.service
sudo journalctl -u kdx-registration-client.service -n 30 --no-pager
```

## Backups and rollback

Private device backup (kept only on the appliance):
`/var/backups/kronoskvm/registration-onboarding-20261031/private-client-state.tar.gz`.
This includes a private key and must never be published or cloned for manufacturing.
The same directory contains original appliance config checksums and agent source hash.

Post-onboarding server backup:
`/var/backups/kdx-registration/onboarding-20261031` contains the database snapshot,
private configuration/signing key and public onboarding summary. Server public
onboarding record: `/root/kdx-registration-real-device-20261031.json`.

To stop this integration without touching the KVM application:
`systemctl disable --now kdx-registration-client.timer`, then stop its service and
close the workstation relay. Keep the private identity and server audit history.
Use an explicit administrator revocation if the license must also be withdrawn;
removing a client file is not server-side revocation. Never overwrite or regenerate
an active identity as part of routine upgrades.
