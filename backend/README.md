# Backend

The FastAPI control plane discovers optional hardware without preventing the
application from starting when a device is absent. It provides appliance
health and inventory, physical-port state, HDMI capture, HID input, serial
console WebSockets, temporary session logs, staged-file management and bounded
system power requests.

Privileged host operations remain outside the API container and are accepted
only through narrowly validated helper interfaces.
