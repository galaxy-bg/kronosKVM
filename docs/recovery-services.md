# Service Port Recovery

Open **Storage → Internal Stage** to upload firmware, then select it
in **Recovery → Published files** and click **Publish selected**. An optional folder groups files by vendor; leave it
empty for devices that require a root-level TFTP filename. Publishing moves the
file without duplicating it. Mounted ISO/IMG files must be ejected first.

Files live at `/mnt/kronoskvm-storage/recovery/` and share the existing 32 GiB
staging quota and operating-system free-space reserve. **Unpublish** removes publication and returns the file to Internal Stage in
**Storage**, where it can be deleted. Existing
files are never overwritten by a move. SHA256 is calculated on demand.

In **Recovery** or **Services**, use **Start**, **Stop**, **Restart**, and **View Logs** for:

- **FTP Recovery**: anonymous read-only downloads on `192.168.34.100:21`.
- **TFTP Recovery**: read-only downloads on `192.168.34.100:69/udp`.
- **HTTP Recovery**: read-only downloads on `192.168.34.100:8080`.

For `hpe/firmware.bin`, use TFTP server `192.168.34.100` with filename
`hpe/firmware.bin`, or HTTP URL
`http://192.168.34.100:8080/hpe/firmware.bin`. The UI provides copy buttons.
HTTP serves files without directory listings; Incoming uploads are not implemented. HTTP clients should use full-file GET downloads (no Range resume).

All three services are available through the existing `br-recovery` bridge, including
recovery Wi-Fi and the service Ethernet port. The separate TFTP process disables
DNS/DHCP and does not restart the appliance's DHCP server. Services are installed
stopped and start on demand; after reboot they remain stopped until started again.

`kronoskvm-service-status.timer` refreshes service states and the latest 100
journal lines every five seconds. The Services screen also refreshes every five
seconds while visible. TFTP logs transfers/errors; HTTP logs client addresses,
paths and response codes. HTTP 200 records response initiation, not proof that
the client received the full file. These logs do not certify a firmware flash.

Install from the deployed checkout with:

```sh
sudo bash /opt/kronoskvm/scripts/install-recovery-services.sh
```

The container installer invokes this automatically. Host dependencies are
`dnsmasq`, `python3`, `python3-pyftpdlib`, and systemd. Rebuild the API and web images when updating UI
or API code. Host service units use numeric UID 10001/GID 20, matching staging.

API:

- `GET /api/v1/recovery`: files and transfer paths.
- `POST /api/v1/recovery/files`: move staged `filename` into optional `folder`.
- `GET /api/v1/recovery/checksum/{path}`: SHA256.
- `POST /api/v1/recovery/restore/{path}`: return to Stage.
- `POST /api/v1/services/{tftp|recovery_http|recovery_ftp}/{start|stop}`: service lifecycle.
- Existing service restart and logs endpoints apply to all recovery services.

## Unified Recovery workspace

The **Storage** menu contains Internal Stage uploads, ISO mount/eject and
External Storage browsing/copying. **Recovery** contains publication, service
controls, connection details and transfer logs. Its **Open Storage** and
**Open External Storage** shortcuts navigate to the corresponding storage area.
The general Services screen continues to manage the same underlying services.

FTP is now available at `192.168.34.100:21`, with user `anonymous` and any password
(e.g. `recovery@`). It is read-only and confined to published Recovery files.
Passive data ports are 30000–30010; active transfers are also supported.
`python3-pyftpdlib` is installed by the host recovery installer when missing.
Use the file's FTP URL or the same relative path shown for TFTP. Start/Stop/Restart
and transfer logs are available directly inside Recovery.

The network section shows service Ethernet link state and unexpired DHCP leases
from the shared service-port/recovery Wi-Fi bridge. Leases do not prove that a
client is currently online. The host publishes a new snapshot every five seconds;
missing or older-than-20-second snapshots are marked unavailable/out of date.

The recovery installer explicitly stops and disables FTP/TFTP/HTTP, including on
reinstallation. Start them manually from Recovery when needed; Start does not
enable automatic startup after a reboot. DHCP remains independent.

## Browse published files

Use **Browse Files** beside **View Logs** on any FTP/TFTP/HTTP card in Recovery
or Services. The browser navigates folders containing published files, shows
file sizes, and copies the selected protocol's URL/path. HTTP files also have
an **Open HTTP** link. Browsing reads the management API and works while transfer
services are stopped; downloading via the protocol requires that service to be
started. FTP and TFTP are browsed through this shared publication inventory,
not through the browser's native protocol support.

Direct links use `/#recovery-browse=tftp`, `/#recovery-browse=recovery_http`, or
`/#recovery-browse=recovery_ftp` on the InfraBox management address.

## Publish multiple files

Select one or more staged files using the checkboxes, or use **Select all** and
**Clear selection**, then click **Publish selected**. The optional folder applies
to every selected file; an empty folder publishes directly at the common root.
No protocol name is required: the same published files are available to each
FTP/TFTP/HTTP service when that service is started.

Each file is processed separately. Successful files remain published even if
another file fails (for example, a filename collision or mounted ISO). The screen
shows one result per file; failed files remain staged and selected for correction
and retry. Existing files are not overwritten.
