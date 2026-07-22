# KronosKVM API

The API listens on `127.0.0.1:8000`. Mutating endpoints are limited to serial
session coordination and the dedicated staging-file directory.

## Endpoints

- `GET /api/v1/health`
- `GET /api/v1/capabilities`
- `GET /api/v1/system/info`
- `GET /api/v1/system/network`
- `GET /api/v1/system/storage`
- `GET /api/v1/system/services`
- `GET /api/v1/hardware/usb`
- `GET /api/v1/hardware/video`
- `GET /api/v1/hardware/serial`
- `GET /api/v1/hardware/rtc`
- `GET /api/v1/hardware/temperature`
- `GET /api/v1/hardware/ports`
- `GET /api/v1/serial/devices`
- `GET /api/v1/storage` — staging capacity and managed file inventory
- `PUT /api/v1/storage/files/{filename}` — stream a raw file upload
- `GET /api/v1/storage/files/{filename}` — download a staged file
- `DELETE /api/v1/storage/files/{filename}` — delete a staged file
- `POST /api/v1/serial/locks`
- `DELETE /api/v1/serial/locks/{device_name}`

Every response includes an `x-request-id` header. A caller-provided
`x-request-id` is preserved. Application request logs are JSON formatted in the
system journal.

Serial lock mutations affect only in-memory coordination state. No endpoint
opens a serial port, writes data, executes shell commands or exposes TCP serial
access.

## Operations

```bash
sudo systemctl status kronoskvm-api
journalctl -u kronoskvm-api
curl http://127.0.0.1:8000/api/v1/health
```
