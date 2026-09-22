# KronosKVM API

The API listens on `127.0.0.1:8000` and is exposed through the Nginx management
gateway. Mutating routes are scoped to application functions; there is no
arbitrary shell endpoint.

## Endpoints

- `GET /api/v1/health`
- `GET /api/v1/capabilities`
- `GET /api/v1/system/info`
- `GET /api/v1/system/network`
- `GET /api/v1/system/storage`
- `GET /api/v1/system/services`
- `POST /api/v1/system/power` — confirmed, allow-listed `reboot` or `poweroff`
- `GET /api/v1/hardware/usb`
- `GET /api/v1/hardware/video`
- `GET /api/v1/hardware/serial`
- `GET /api/v1/hardware/rtc`
- `GET /api/v1/hardware/temperature`
- `GET /api/v1/hardware/ports`
- `GET /api/v1/serial/devices`
- `GET /api/v1/hid/status`
- `WS /api/v1/hid/ws` — keyboard and relative mouse reports
- `GET /api/v1/video/status`
- `GET /api/v1/video/stream.mjpg`
- `GET /api/v1/storage` — staging capacity and managed file inventory
- `PUT /api/v1/storage/files/{filename}` — stream a raw file upload
- `GET /api/v1/storage/files/{filename}` — download a staged file
- `DELETE /api/v1/storage/files/{filename}` — delete a staged file
- `GET /api/v1/storage/tasks` — background task state
- `DELETE /api/v1/storage/tasks/{task_id}` — request cancellation
- `GET /api/v1/storage/virtual-media` — attached/ejected media state
- `POST /api/v1/storage/virtual-media` — attach a staged ISO/IMG read-only
- `DELETE /api/v1/storage/virtual-media` — eject the active virtual medium
- `GET /api/v1/tasks` — temporary unified application/session task history
- `DELETE /api/v1/tasks/completed` — clear completed task rows
- `GET /api/v1/network/settings` — configurable wired-interface inventory
- `POST /api/v1/network/settings` — stage a confirmed DHCP/static IPv4 change
- `GET /api/v1/logs` — grouped structured application/audit events
- `GET /api/v1/session-logs` — temporary downloadable session files
- `GET /api/v1/connections` — list saved network connection profiles
- `POST /api/v1/connections` — create a password-free connection profile
- `PUT /api/v1/connections/{id}` — update a connection profile
- `DELETE /api/v1/connections/{id}` — delete a connection profile
- `POST /api/v1/serial/locks`
- `DELETE /api/v1/serial/locks/{device_name}`

Every response includes an `x-request-id` header. A caller-provided
`x-request-id` is preserved. Application request logs are JSON formatted in the
system journal.

Every mutating HTTP response also includes `x-kronos-task-id`. Task lifecycle
events are structured application-log records. Uploads reuse this identifier
for progress, while SSH, serial and HID WebSocket tasks remain active until the
session ends.

Power requests are written as an exact action marker in `/state`. A root-owned
systemd path/service pair accepts only `reboot` and `poweroff`; the API container
does not receive systemd, DBus, Docker-socket or general root access.

## Operations

```bash
sudo systemctl status kronoskvm-containers
sudo journalctl -u kronoskvm-containers
curl http://127.0.0.1:8000/api/v1/health
```
