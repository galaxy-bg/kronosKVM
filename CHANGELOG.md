# Changelog

## Unreleased

- Standardize current product documentation on **KDX InfraBox — Infrastructure
  in a Box**; retain the historical `kronosKVM` repository and `kronoskvm-*`
  technical identifiers for compatibility.
- Document implemented HTTPS, Remote Assist, USB WAN and installation limits.
- Add WireGuard Remote Assist configuration, connection control, startup
  preference, handshake/traffic status and private VPN access address.
- Add phone USB WAN and External Storage / WAN status with USB IP/gateway and
  separate VPN information.
- Improve mobile KVM layouts and add a footer Caps Lock control.
- Add internal Storage SHA256 verification and virtual-media boot/watcher fixes.

- Add confirmed Force Eject controls for target-locked virtual media; preserve
  backing-file protection after failed eject and block overwrite while in use.
- Show sampled virtual-media read activity, speed, last-read time and USB
  disconnection in KVM and Storage, with unavailable telemetry distinguished from idle.
- Mount oversized hybrid ISOs as read-only USB disks to avoid the Linux gadget
  CD-ROM size limit; Ubuntu boot and OS installation start verified on hardware.
- Browse published Recovery files per service and keep FTP/TFTP/HTTP disabled by default.
- Show USB copy byte progress in Tasks and Background tasks using a shared task ID;
  Copy & Mount displays a separate mounting phase and waits for the requested ISO.
- Restore standalone Storage navigation with Recovery shortcuts to Internal/External storage.

- Add checkbox-based multi-file publication with Select all, per-file results and
  retry selection for files that could not be published.

- Fix Background tasks rendering and completion for service actions; automatically
  dismiss successful service entries and reconcile results from the task endpoint.
- Wrap Recovery file URLs and actions; clarify that the publication folder is optional.

- Consolidate staging uploads, USB imports, published files, transfer controls and
  logs under Recovery; show service Ethernet link state and current DHCP leases.
- Add read-only anonymous FTP on the recovery network, with passive/active
  transfers and Start/Stop/Restart controls alongside TFTP and HTTP.

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
