# Service Port Recovery

Open **Storage** to upload a firmware/image, then **Service Port** to select it
and move it into Recovery. An optional folder groups files by vendor; leave it
empty for devices that require a root-level TFTP filename. Publishing moves the
file without duplicating it. Mounted ISO/IMG files must be ejected first.

Files live at `/mnt/kronoskvm-storage/recovery/` and share the existing 32 GiB
staging quota and operating-system free-space reserve. **Move to Stage** removes
publication and returns the file to Storage, where it can be deleted. Existing
files are never overwritten by a move. SHA256 is calculated on demand.

In **Services**, use **Start**, **Stop**, **Restart**, and **View Logs** for:

- **TFTP Recovery**: read-only downloads on `192.168.34.100:69/udp`.
- **HTTP Recovery**: read-only downloads on `192.168.34.100:8080`.

For `hpe/firmware.bin`, use TFTP server `192.168.34.100` with filename
`hpe/firmware.bin`, or HTTP URL
`http://192.168.34.100:8080/hpe/firmware.bin`. The UI provides copy buttons.
HTTP serves files without directory listings; FTP and incoming uploads are not
implemented. HTTP clients should use full-file GET downloads (no Range resume).

Both services are available through the existing `br-recovery` bridge, including
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
`dnsmasq`, `python3`, and systemd. Rebuild the API and web images when updating UI
or API code. Host service units use numeric UID 10001/GID 20, matching staging.

API:

- `GET /api/v1/recovery`: files and transfer paths.
- `POST /api/v1/recovery/files`: move staged `filename` into optional `folder`.
- `GET /api/v1/recovery/checksum/{path}`: SHA256.
- `POST /api/v1/recovery/restore/{path}`: return to Stage.
- `POST /api/v1/services/{tftp|recovery_http}/{start|stop}`: service lifecycle.
- Existing service restart and logs endpoints apply to both recovery services.
