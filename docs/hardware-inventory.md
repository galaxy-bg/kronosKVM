# Hardware Inventory

Status: initial read-only inventory completed on 2026-07-16. The private raw
report remains local under `artifacts/inventory/` and is not committed.

## Confirmed

- Hostname: `kdx-ikvm`
- SSH user: `kronosdx`; public-key authentication works
- Management address: `192.168.31.145/24` on `wlan0`
- OS: Debian GNU/Linux 11 Bullseye
- Kernel: Linux `6.1.21-v8+`, aarch64
- Board: Raspberry Pi Compute Module 4 Rev 1.1
- CPU: four Cortex-A72 cores, up to 1.5 GHz
- Memory: approximately 3.7 GiB usable
- Storage: approximately 29 GiB ext4 root on `/dev/mmcblk0p2`; vfat `/boot`
- Root filesystem usage: approximately 4.3 GiB of 29 GiB
- `eth0`: native CM4 Ethernet controller path, no carrier during inventory
- `eth1`: USB Realtek RTL8152 adapter, no carrier during inventory
- `wlan0`: active management interface and default route via `192.168.31.1`
- USB topology: internal seven-port USB 2.0 hub, HID receiver and RTL8152
- I2C: `/dev/i2c-20`, `/dev/i2c-21`
- GPIO: `/dev/gpiochip0`, `/dev/gpiochip1`
- Temperature: 50.1°C during inventory
- Throttling: `0x0`, no throttling flags
- Timezone: Europe/Istanbul; NTP synchronized
- Listening remotely: SSH on TCP 22
- Local-only listener: CUPS on TCP 631
- mDNS/Avahi traffic observed on UDP 5353

## Hardware state

- No `/dev/ttyUSB*` or `/dev/ttyACM*` serial adapters detected.
- No `/dev/rtc*` device detected and `timedatectl` reported RTC unavailable.
- `/sys/class/udc` was empty; USB gadget mode is not currently available.
- No configured USB gadgets were present.
- Kernel codec/ISP video nodes exist, but no `/dev/video0` capture device.
- `v4l2-ctl` found only BCM2835 codec/ISP and RPivid devices.
- Camera report: unsupported/not detected with no libcamera interfaces.
- PCIe controller reported link down; M.2 function remains unverified.
- One failed service: `bthelper@hci0.service`.

## Unverified

- Physical chassis mapping for ETH0, ETH1 and USB1-3
- Whether storage is removable microSD or a carrier-specific route
- SLAVE-port controller wiring and required device-tree configuration
- CAM0/CAM1 and DISP routing
- RTC chip presence, wiring and required overlay
- Exact M.2 electrical interface
- Carrier-board Wi-Fi 6 hardware versus the active CM4 `wlan0`
