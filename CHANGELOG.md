# Changelog

## Unreleased

- Add Service Port Recovery folders, staging moves, shared quota and SHA256 checks.
- Add on-demand read-only TFTP/HTTP services with Start/Stop/Restart and transfer logs.
- Refresh host service status/logs automatically and expose them in the Logs view.
- Add Virtual Media watcher restart and logs to Services.

- Add read-only External Storage browsing, downloads, copy-to-stage and Copy & Mount.
- Account for active uploads in available staging capacity; show insufficient-space
  reasons before external copies while retaining the 32 GiB quota and 10 GiB reserve.
- Fix virtual-media eject to clear the backing file and report host helper errors.
- Preserve accumulated mouse movement, add adjustable sensitivity (default 0.2x),
  and reduce video pipe buffering.
- Improve snapshot and browser recording cleanup, format selection and size/time limits.
  **Known issue:** the operator still reports frozen video recordings after the latest
  fresh-JPEG recording change; recording is not validated as working. MP4 depends on
  browser MediaRecorder support, with WebM fallback.


- Fix direct-HDMI capture compatibility on the two-lane X630 using a persistent
  EDID that prefers 720p60 and retains 1080p30 and legacy PC modes. Document
  source-PC restart requirements for BIOS, PS5 HDCP setup, and pending device
  compatibility tests.

- Establish the prototype repository, documentation and FastAPI skeleton.
- Add read-only local and remote hardware inventory tooling.
- Add idempotent base OS preparation and current-release update workflows.
- Apply and verify the available Bullseye security package updates.
- Add and deploy the localhost-only read-only system and hardware health API.
- Add serial adapter discovery, profiles and exclusive in-memory session locks.
- Add the persistent isolated `kronosKVM` Wi-Fi management access point.
- Add the hybrid Docker Compose application-plane foundation.
- Deploy the hardened ARM64 API container while preserving the host-managed AP
  and disabled routing policy.
- Establish ETH0-first development policy, mDNS discovery and a safe
  `kronoskvm status` command.
- Add the AP-only development dashboard and localhost API reverse proxy.
- Restyle the development dashboard with the light KronosDX interface language.
- Confirm and name the chassis USB, console and KVM OTG port topology.
- Show the verified physical port map and USB mux limitation in the dashboard.
- Replace raw hardware capabilities with product-focused KVM service readiness.
- Add live connected/disconnected physical port inventory and safe console
  action placeholders.
- Prevent stale frontend assets from hiding API and service status after deploys.
- Isolate dashboard data and render failures so healthy APIs are never reported
  unavailable because of a client-side section error.
- Switch development assets to versioned filenames to bypass persistent browser
  caches completely.
- Introduce the globe-and-connectivity KronosKVM product mark and
  “All-in-One IP-KVM System” identity.
- Replace the provisional vector mark with the operator-supplied product logo
  PNG without altering its pixels.
