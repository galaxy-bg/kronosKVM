# Second appliance installation

For the latest application deployment, see the
[2026-10-04 update record](second-appliance-update-20261004.md).

## Target and source

The second appliance was provisioned on 2026-09-26 from a clean Raspberry Pi OS
64-bit installation: Debian 13, Raspberry Pi 4 Model B Rev 1.5, kernel
`6.18.50+rpt-rpi-v8`, 64 GB microSD. Source was cloned from the GitHub `main`
branch at `b073a464ead82c088004b237a81a1d9efca3b131` into
`/root/infrabox-source`; runtime files are installed under `/opt/kronoskvm`.

## Clean-install gaps

The existing `install-dependencies.sh` still stops at an obsolete OS-baseline
check. For this installation, dependencies were installed explicitly before
running `install-containers.sh`:

```sh
bash scripts/bootstrap.sh
apt-get update
apt-get install -y docker.io docker-compose dnsmasq v4l-utils i2c-tools \
    python3-pyftpdlib wireguard-tools
bash scripts/install-containers.sh
cd /opt/kronoskvm
bash scripts/install-usb-wan.sh
bash scripts/install-remote-assist.sh
```

The application installer generates a separate HTTPS certificate. No WireGuard
identity or customer data is copied from the first appliance.

Boot configuration was backed up before adding the `dwc2,dr_mode=peripheral`
and `tc358743` overlays under `[all]`. The installed board model must be
confirmed before configuring any RTC overlay or power daemon.

The management network uses NetworkManager with `br-recovery` at
`192.168.34.100/24`, and a Wi-Fi AP named `KronosDX-iKVM-02` to distinguish this
unit from the first prototype. DHCP is restricted to the Recovery bridge;
Ethernet remains the existing DHCP uplink. Service USB Ethernet is matched by
physical USB topology. USB phone WAN uses its own profile. The AP retains the
prototype's open-network policy.

This record does not establish successful HDMI, HID, RTC or VPN operation;
each requires its corresponding hardware or unique VPN profile and validation.

## Validation results

After a reboot, both API and web containers reported healthy; systemd reported
no failed units. HTTP API health and HTTPS page access were verified from the
operator Mac. Application-user storage write/read/delete passed. The Recovery
bridge retained its address and dnsmasq, service-status and Remote Assist timers
were active. Remote Assist reported installed/off with no profile and Ethernet
as the current uplink.

The TC358743 capture bridge initialized successfully on `/dev/v4l-subdev0`,
with `/dev/video0` present. `fe980000.usb` and both HID character devices were
present. At validation time HDMI reported no signal and OTG reported
`not attached`; end-to-end video and keyboard/mouse operation remain untested.
No `/dev/rtc*` device was present. RTC board identification/configuration and a
separate WireGuard profile remain outstanding.
