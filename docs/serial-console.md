# Serial Console

KronosKVM supports browser serial sessions for Cisco, Aruba, HPE Comware,
Ruijie, Zyxel, Linux and generic console devices. The default profile is auto
baud with 8N1 and no flow control; common rates from 9600 through 115200 are
available manually.

The API discovers `/dev/ttyUSB*` and `/dev/ttyACM*`, resolves the stable USB
topology, opens exclusive sessions and streams terminal data over WebSocket.
The UI supports auto-detection, reconnect, configurable line settings and
explicit temporary session logging.

## Physical assignments

- Console 1: black USB-A 2.0, topology `1-1.3`
- Console 2: black USB-A 2.0, topology `1-1.4`

The PL2303 adapter used during verification appeared as `/dev/ttyUSB0`.
`/dev/serial/by-id` remains preferable when an adapter exposes a unique serial
number.

Session transcripts are written only after the operator presses **Start log**.
They are staged under the API container's temporary filesystem, can be
downloaded from Session Logs and are allowed to disappear on API/appliance
restart. Terminal payloads are not copied into the persistent application log.
