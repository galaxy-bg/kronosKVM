# Implementation Log

## 2026-07-16

- Created the public GitHub repository and initial prototype.
- Adopted the detailed KronosKVM engineering specification.
- Began Milestone 0 structure and read-only Milestone 1 tooling.
- Configured local SSH public-key access without storing a password.
- Verified the target host as `kdx-ikvm` and completed read-only inventory.
- Confirmed Debian 11, CM4 Rev 1.1, 4 GB class memory and Wi-Fi management.
- Found no registered UDC, RTC, serial or HDMI capture hardware.
- No target package, boot, network, firewall, gadget or service changes performed.

## Milestone 2

- Reviewed OS, time, journal, firewall, user and filesystem state.
- Confirmed passwordless sudo, persistent journal, synchronized NTP and
  Europe/Istanbul timezone.
- Deferred package installation and firewall changes because Bullseye is not
  the production baseline and chassis Ethernet mapping is incomplete.
- Created the locked `kronoskvm` service account and protected application,
  configuration, data, image, log and runtime directories.
- Added tmpfiles runtime creation and bounded persistent journal retention.
- Verified SSH remained reachable; no reboot was required.

## OS maintenance

- Adopted current-release `apt full-upgrade` with pre-update configuration
  backup.
- Kept APT release codenames unchanged.
- Documented clean Raspberry Pi OS Lite 64-bit imaging for major migration.
- Reviewed the full-upgrade simulation and disabled automatic package removal.
- Applied the Bullseye current-release update on 2026-07-16:
  `libxfont2`, `p7zip`, `p7zip-full` and `wireless-regdb`.
- Removed no packages and changed no APT release codenames.
- Stored a root-only pre-update backup under `/var/backups/kronoskvm/`.
- Rebooted successfully; SSH and `192.168.31.145` Wi-Fi management returned.
- Verified no pending package upgrades, no throttling and synchronized NTP.
- The existing `bthelper@hci0.service` failure remains for later OS migration
  review.

## Milestone 3

- Implemented typed read-only FastAPI endpoints for health, capabilities,
  system, network, storage, services and optional hardware.
- Added request IDs, structured JSON application logs and safe error responses.
- Added Python 3.9 compatibility for the current Bullseye device.
- Installed `kronoskvm-api.service` as the locked `kronoskvm` user.
- Bound the service exclusively to `127.0.0.1:8000`.
- Verified all API endpoints on the CM4 using real system data.
- Confirmed the service is enabled, active and stable with zero restarts after
  the Python 3.9 compatibility fix.
- Updated deployment to restart the API explicitly after application upgrades,
  ensuring new code replaces the running process.

## Milestone 4

- Added USB serial discovery for `/dev/ttyUSB*` and `/dev/ttyACM*`.
- Added VID, PID, serial number, kernel driver and stable by-id/by-path metadata.
- Added 9600, 19200, 38400 and 115200 8N1 profiles.
- Added exclusive in-memory device locks with token-based release.
- Installed PySerial 3.5 and granted the service supplementary `dialout` access.
- Verified the no-adapter state on the CM4: empty inventory and
  `not_detected` capability.
- Verified unknown devices cannot be locked.
- Confirmed TCP ports 2001 and 2002 remain closed.
- No serial device was opened and no serial data was read or written.

## Network mapping

- Confirmed chassis ETH0 maps to Linux `eth0`.
- Confirmed DHCP address `192.168.31.144/24`, gateway/DNS `192.168.31.1`.
- Verified independent SSH and API service reachability over Ethernet.
- Established Ethernet as the recovery path for the planned Wi-Fi AP change.

## Persistent management AP

- Installed hostapd and dnsmasq.
- Configured `wlan0` as WPA2 access point `kronosKVM`.
- Assigned `192.168.34.100/24` and DHCP pool
  `192.168.34.150-192.168.34.220`.
- Kept `eth0` as the preferred customer/internet route.
- Enabled DNS forwarding only on loopback and the AP address; routing, NAT and
  bridging remain disabled.
- Stored the WPA passphrase only in root-readable hostapd configuration.
- Verified hostapd, dnsmasq and KronosKVM API services are active.

## Containerized application plane

- Installed the distribution Docker Engine and Docker Compose packages.
- Disabled Docker bridge creation, iptables management, IP forwarding and
  masquerading before starting the daemon.
- Built the FastAPI image natively on the CM4 as ARM64.
- Limited host networking to the build step and the localhost-only API runtime.
- Deployed the API as UID/GID `10001` with a read-only root filesystem, all
  capabilities dropped and `no-new-privileges`.
- Exposed only narrow read-only host paths for system and CM4 device-tree
  discovery; no Docker socket or broad device mount is present.
- Disabled the native API service while retaining it as a rollback path.
- Rebooted and verified Docker, the container service, hostapd and dnsmasq
  return automatically.
- Confirmed the API reports the CM4 model, host interfaces and temperature.
- Confirmed `192.168.31.144/24` on `eth0` and `192.168.34.100/24` on `wlan0`
  remain unchanged after reboot.
- Confirmed IPv4 forwarding is `0`, `docker0` is absent and Docker added no NAT
  rules.

## ETH0-first development access

- Adopted chassis ETH0 as the primary update, package, Git, image-pull and
  deployment path.
- Preserved the permanent Wi-Fi AP as an isolated recovery path at
  `192.168.34.100`; hostapd and dnsmasq were not restarted or reconfigured.
- Changed the appliance hostname from the prototype name to `kronoskvm`.
- Restarted only Avahi and verified `kronoskvm.local` resolves to the current
  ETH0 DHCP address from the development Mac.
- Updated the local `kronoskvm` SSH alias to prefer `kronoskvm.local`.
- Added and installed `kronoskvm status` under `/usr/local/bin`.
- Verified the command reports AP, ETH0, gateway, upstream DNS, ETH0 internet
  reachability and container state without reading secret configuration.
- Performed no reboot.

## AP-only development frontend

- Added a static responsive system dashboard and same-origin API client.
- Added a hardened Nginx web container with a read-only root filesystem,
  `no-new-privileges` and a minimal capability set.
- Bound Nginx only to `192.168.34.100:80`.
- Proxied `/api/` to the FastAPI service on `127.0.0.1:8000`.
- Built and deployed the web image over ETH0 without restarting Docker,
  hostapd, dnsmasq or either network interface.
- Verified the dashboard and API health endpoint return HTTP 200 on the AP
  address.
- Verified port 80 remains closed on the current ETH0 DHCP address.
- Confirmed IPv4 forwarding remains disabled and performed no reboot.
- Restyled the dashboard with a responsive light theme, mint-green KronosDX
  accents, summary cards, navigation shell and fixed appliance status bar.

## Physical USB mapping

- Used the same known HP HID dongle to map each chassis USB host port.
- Confirmed USB1 as `1-1.1` and assigned it to Console 1.
- Confirmed USB2 as `1-1.2` and assigned it to Console 2.
- Confirmed USB3 as `1-1.3` and assigned it to service/maintenance use.
- Confirmed USB ETH1 as `1-1.5`.
- Confirmed that connecting USB-C `SLAVE` removes the internal hub and ETH1;
  disconnecting it restores them.
- Identified USB-C `SLAVE` as the KVM OTG candidate, with DWC2 peripheral mode
  and UDC activation still pending.
- Added the verified Console 1, Console 2, Service USB, ETH1 and KVM OTG
  assignments to the AP dashboard.
- Replaced raw capability names such as RTC and serial with user-facing KVM
  readiness for web access, console ports, KVM OTG and video input.
