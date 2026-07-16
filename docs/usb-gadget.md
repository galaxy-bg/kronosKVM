# USB Gadget

The USB-C `SLAVE` port is expected to provide OTG/device mode. This is
unverified. The first inventory found `otg_mode=1` under the CM4 boot section,
but `/sys/class/udc` was empty. No gadget was configured. Identify the physical
controller and required device-tree setup before enabling anything. Future
composite functions may include keyboard, relative mouse, absolute mouse and
read-only-first mass storage.
