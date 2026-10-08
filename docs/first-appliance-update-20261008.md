# First appliance update — 2026-10-08

Updated `192.168.31.185` from commit `0775c0e`. Built and validated ARM64 API/web
images on the appliance, then reloaded the container service. Installed the
AP-access host units with the fresh policy **disabled**. No OS update or reboot
was performed. Existing guacd was retained.

## Included changes

- Default-off Settings control for Wi-Fi-to-Ethernet IPv4 access and CIDR limits.
- Profile-independent Wi-Fi status and restart resolution.
- Complete-JPEG browser display, last-frame pause and reconnect behavior.
- Scoped LCD API support is present in the API image; no LCD provisioning,
  service activation, backlight wiring or Witty firmware changes were applied.
  This appliance had no vendor LCD driver directory and its LCD service was inactive.

## Recovery

- Backup: `/var/backups/kronoskvm/pre-first-update-0775c0e.tzkl9h`.
- `application.tar.gz`: previous application source.
- `private-state-config.tar.gz`: private credentials and device configuration;
  keep root-only.
- `dns-config.tar.gz`: original DNS configuration before the first-box adaptation.
- Installer DNS backup: `/var/backups/kronoskvm/ap-access-install.L8hEAs`.
- Previous API/web tags: `kronoskvm-api:pre-first-update-0775c0e` and
  `kronoskvm-web:pre-first-update-0775c0e`.
- Updated API/web tags: `kronoskvm-api:first-update-0775c0e` and
  `kronoskvm-web:first-update-0775c0e`, also tagged `:dev`.

For rollback, disable/stop the newly installed AP-access boot/path/timer units,
remove only `bridge kdx_ap_ingress` and `inet kdx_ap_access`, restore the original
DNS archive and remove the newly generated `kdx-ap-access.conf`, then restart
dnsmasq. Restore application source and previous image tags, and reload
`kronoskvm-containers.service`. Preserve the existing guacd container. Do not
restore private state unless a separate device-configuration rollback is intended.

## First-box DNS adaptation

The first box already advertised `192.168.34.100` for local DNS, unlike the
second-box installation. Its existing untagged DNS option was scoped to
`tag:br-recovery` before installing the dynamic AP-access options. This preserves
local-name resolution when customer-network access is disabled. Dnsmasq tags
requests with their arrival interface and prefers matching tagged options;
see the [official tag-system documentation](https://dnsmasq.org/docs/dnsmasq-man.html).

## Validation

- The uploaded source archive matched SHA256
  `da972c1524dc8ad1c3b6732a0df05b56c216c81ec691552edd2a5be19b680b8d`.
- New-image authentication, remote-route and AP-access-route smoke checks passed;
  nginx configuration validation passed.
- API, web and guacd became healthy; no failed systemd units were reported.
- Live Chrome verified administrator login, the Settings AP-access form in
  disabled state, active Wi-Fi reporting and the complete-frame helper, with
  no page errors. Diagnostic login was logged out.
- The host policy is off, NAT has no permit rule, and global IPv4 forwarding
  remains zero. No production routing-enable test was performed.
- Credentials, saved connection profiles, TLS and Remote Assist configuration
  matched the private backup byte-for-byte.
- Direct DNS query resolved `kdx-infrabox.local` to `192.168.34.100`.
- Anonymous management requests still return 401.
- Capture device is present but reports no HDMI signal. Real target KVM display
  validation on this appliance remains pending a connected video source.

The published source commit passed 177 tests and lint before deployment. See
[AP customer-network access](ap-customer-access.md) and
[video capture](video-capture.md) for implementation and validation limits.
