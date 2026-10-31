# InfraBox KVM update — 2026-10-17

Appliance: `infrabox-000865dd`, LAN `192.168.1.107`.

## Findings

The TC358743 capture device and stored EDID were present. Reapplying capture
configuration and reseating the original HDMI cable left `power_present: 0` and
the timing query reported no link. After the user replaced the cable, the card
reported `power_present: 1` and 1024 × 768 at 60 Hz. This isolates the observed
missing-input condition to the original cable/connection path; long-term freeze
behavior has not yet been qualified.

## Deployed changes

The API now releases the capture lock after startup errors and terminates an
encoder that produces no complete JPEG for eight seconds. The browser detects
a stream without a complete frame for ten seconds and uses the existing retry
flow. Video status distinguishes cable power detection from valid video timing.
The displayed frontend version is 0.3.46.

Only API/web containers were refreshed. Configuration hashes were unchanged;
LCD orientation and Witty Pi services remained active. API, web and guacd were
healthy after deployment.

## Validation and rollback

- 295 tests passed in the sandbox. The remaining real SSH integration test
  passed with permission to bind its loopback test server (296 total).
- Ruff and JavaScript syntax checks passed.
- The installed API, running as its regular container user, captured 233 complete
  JPEG frames over 22.1 seconds from the actual HDMI source. Closing the stream
  released its capture lock and stopped ffmpeg.
- Browser playback and sustained operation still need user confirmation.

Root-only source backup and build logs:
`/var/backups/kronoskvm/pre-kvm-20261017.lgOq1s`.
Previous images: `kronoskvm-api:pre-kvm-20261017` and
`kronoskvm-web:pre-kvm-20261017`. To roll back, restore the source archive,
retag those images as `:dev`, and run `/opt/kronoskvm/scripts/start-containers.sh`.
The deployment did not reboot the appliance or alter VPN configuration.
