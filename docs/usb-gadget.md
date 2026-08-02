# USB Gadget

The USB-C connector is assigned exclusively to KVM OTG/device mode. Boot config
uses:

```ini
[all]
dtoverlay=dwc2,dr_mode=peripheral
```

The registered UDC is `fe980000.usb`. `scripts/setup-hid-gadget.sh` builds a
small ConfigFS composite gadget designed for the Pi 4 DWC2 controller:

- `/dev/hidg0`: 8-byte boot keyboard
- `/dev/hidg1`: 3-byte BIOS-compatible relative boot mouse

An earlier three-interface keyboard/absolute-mouse/relative-mouse profile
caused DWC2 endpoint shutdowns during testing. The two-interface profile avoids
that unstable third periodic endpoint.

UDC state meanings used during diagnosis:

- `not attached`: gadget is ready but no powered USB host is connected
- `configured`: the target host enumerated and configured the gadget

The four USB-A host ports remain independent while USB-C operates in device
mode. Virtual-media staging is active, but USB mass-storage attachment is not
yet part of the gadget.

## Power warning

GPIO power and target USB VBUS must not be treated as isolated supplies. The
final power board must prevent backfeed and provide correct power sequencing.
Until then, boot the appliance before attaching the target OTG cable.
