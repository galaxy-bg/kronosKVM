# Serial Console

Initial support targets Cisco, Aruba, HPE Comware, Zyxel, Linux and generic
devices. Default profile is 9600 8N1 without flow control. Discovery will inspect
`/dev/ttyUSB*`, `/dev/ttyACM*`, VID/PID, serial, driver and stable udev path.
TCP exposure remains disabled during initial phases.
