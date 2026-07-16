# Serial Console

Initial support targets Cisco, Aruba, HPE Comware, Zyxel, Linux and generic
devices. Default profile is 9600 8N1 without flow control. Discovery will inspect
`/dev/ttyUSB*`, `/dev/ttyACM*`, VID/PID, serial, driver and stable udev path.
TCP exposure remains disabled during initial phases.

## Milestone 4 foundation

The API discovers adapters without opening them:

- `GET /api/v1/serial/devices`
- `POST /api/v1/serial/locks`
- `DELETE /api/v1/serial/locks/{device_name}`

Locks are exclusive and return a random release token. Unknown devices cannot be
locked. Lock state is intentionally in-memory and clears on service restart.

The `kronoskvm` service receives supplementary `dialout` group membership, but
there is no endpoint for opening, reading or writing a serial port yet. TCP
serial exposure remains disabled.

Supported initial profiles are 9600, 19200, 38400 and 115200 baud, all using
8N1 without flow control.
