# USB Gadget

The USB-C `SLAVE` port is physically confirmed as the KVM OTG/device candidate.
Connecting it removes the carrier's internal USB host hub and USB ETH1 from the
CM4 topology; disconnecting it restores them. This indicates a carrier-level
USB host/device mux.

The current boot configuration uses `otg_mode=1`, so `/sys/class/udc` remains
empty and the connected Mac does not enumerate a KronosKVM USB device. No
gadget has been configured. DWC2 peripheral mode must be enabled and verified
before creating keyboard, relative mouse, absolute mouse or read-only-first
mass-storage functions.

USB1-3 and ETH1 must be treated as unavailable while KVM OTG is selected unless
later hardware testing proves simultaneous operation.
