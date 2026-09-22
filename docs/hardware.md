# Hardware

The active prototype uses a Raspberry Pi 4 Model B Rev 1.5 with a Geekworm X630
HDMI-to-CSI bridge and a 64 GB microSD card. The earlier CM4 carrier prototype
is retired and is not the current deployment target.

## Active modules

- Native Ethernet and integrated Wi-Fi
- Four independent USB-A host ports
- USB-C DWC2 device controller for KVM keyboard and mouse
- X630/TC358743 on CSI-2 for HDMI capture
- Two USB serial-console adapters supported on the black USB 2.0 ports
- Internal 32 GiB staging allocation on the root filesystem

## Pending modules

- RTC and managed power-control board
- Final isolated appliance power input
- Enclosure and labelled service/storage ports
- Optional USB Ethernet adapter on the Service USB 3.0 port

The current GPIO 5V power arrangement is for prototype testing only. The final
power design must prevent backfeed between the appliance supply and target USB
VBUS while preserving the VBUS sensing required for USB gadget attachment.
