# Appliance update — 2026-10-15

Updated the Ethernet-connected appliance at `192.168.31.26` using local
`f68aaff` application sources plus the existing production serial/model display
changes. GitHub `origin/main` was checked and remains at the older September 22
commit `b073a46`. No OS package upgrade or reboot was performed.

Built API/web images on the ARM64 appliance and installed device identity and
Wi-Fi host services. The Wi-Fi installer initially encountered its missing
identity-service dependency; installing identity and rerunning Wi-Fi completed
successfully. Existing guacd was retained.

- Hostname: `infrabox-000865dd`.
- SSID: `KDX-iKVM-000865dd`.
- Hardware serial: `10000000000865dd`; displayed model: `Galaxy-RP4`.
- Recovery directory: `/var/backups/kronoskvm/pre-update-20261015`.
- Root-only archives: `application.tar.gz` and `private-state-config.tar.gz`.
- Previous images: `kronoskvm-api:pre-update-20261015` and
  `kronoskvm-web:pre-update-20261015`.
- New images: `kronoskvm-api:update-20261015` and
  `kronoskvm-web:update-20261015`, also tagged `dev`.
- Identity migration backup: `/var/backups/kronoskvm/device-identity-m94wahn8`.

Validation: 212 local tests and lint passed. API, web and guacd containers are
healthy; identity, Wi-Fi and LCD services are active; systemd reports no failed
units. Nginx configuration passes, HTTPS returns 200, health reports the new
hostname, and anonymous system-info requests return 401. The existing scoped
LCD credential successfully reads system info and network info. TLS files,
administrator authentication state and Remote Assist configuration match the
backup byte-for-byte. Ethernet retains `192.168.31.26`.

Physical LCD visibility, Wi-Fi client association and real target HDMI/HID
operation were not tested. No administrator password was reset.

Rollback requires disabling the newly installed identity/Wi-Fi units and removing
their container dependencies before restoring the previous source/image tags.
Restore hostname/AP settings from the migration backup if reverting names;
reload containers afterward. Keep private archives root-only and restore private
state only when intentionally reverting device configuration.
