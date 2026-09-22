# USB phone WAN — first-stage bring-up

The Raspberry Pi 4 Storage USB-A port can accept phone tethering instead of a disk.
This phase provides a host NetworkManager DHCP profile and a diagnostic command;
it does not yet implement the Remote Assist page, VPN, or public web access.

Install on the appliance:

```sh
sudo bash /opt/kronoskvm/scripts/install-usb-wan.sh
```

The installer backs up NetworkManager profiles under
`/var/backups/kronoskvm/usb-wan/<timestamp>/`, loads existing tethering drivers,
and installs iPhone pairing utilities. Kernel drivers auto-load on subsequent
USB attachment. No reboot or NetworkManager restart is required.

`KDX-USB-WAN` matches the physical Storage port (USB 2 path `1-1.1` or USB 3
path `2-1`) AND a supported network driver (`rndis_host`, `cdc_ether`, `cdc_ncm`,
`ipheth`). USB hubs beneath that port and generic USB Ethernet adapters are not
yet supported by this initial profile. A disk does not match the network profile.

The existing Recovery Service profile is constrained to its physical Service
port, so an iPhone named `eth1` cannot be attached to the recovery bridge just
because of its interface name. Running Ethernet/AP connections are not restarted.

IPv4 DHCP routes and DNS use priority/metric 600. Existing Ethernet (metric 100)
remains preferred; USB becomes a default route when Ethernet's default route is
absent. This is not internet-health-based failover: an Ethernet link with a dead
upstream still wins. IPv6 is disabled on this initial USB WAN profile.

## Phone test

1. Connect a data-capable cable to the Storage USB-A port.
2. Android: enable mobile data and USB tethering. iPhone: enable Personal Hotspot,
   unlock the phone and approve its Trust prompt when shown.
3. Run `sudo python3 /opt/kronoskvm/scripts/check-usb-wan.py --probe`.
4. Verify `storage_port: true`, profile `KDX-USB-WAN`, a DHCP address and gateway,
   and `internet_ipv4.ok: true` with HTTP 200.
5. Unplug/replug and confirm DHCP and the probe recover automatically.

The HTTPS probe explicitly binds the USB interface and disables proxies. It uses
an IP-literal HTTPS endpoint so Ethernet connectivity or system DNS cannot produce
a false positive. DNS through the phone and WireGuard remain separate validation
steps. Do not report an end-to-end pass until an actual phone has passed the probe.

To disable USB WAN without affecting Ethernet/AP:

```sh
sudo nmcli connection modify KDX-USB-WAN connection.autoconnect no
sudo nmcli connection down KDX-USB-WAN
```

For full profile rollback, restore the saved system-connections directory contents
as root (preserving file permissions), remove the new KDX-USB-WAN profile with
`nmcli connection delete KDX-USB-WAN`, then run `nmcli connection reload`.
Do not print saved profiles: they may contain existing Wi-Fi secrets.

## 2026-09-22 live phone validation

Samsung Galaxy (`04e8:6863`, tethering mode) detected on Storage path `1-1.1`.
`rndis_host` created `usb0`; `KDX-USB-WAN` activated automatically and received
IPv4 address `10.161.147.177/24`, gateway/DNS `10.161.147.83`.
The explicit USB-bound, proxy-disabled HTTPS IP probe returned HTTP 200 while
Ethernet remained the preferred default route. Ethernet `.112` and recovery
bridge `.100` remained up. Unplug/replug recovery and iPhone hardware validation
remain pending.

A DNS query bound to `usb0` against the phone's DHCP DNS returned two A answers;
HTTPS to `example.com` using that answer (`curl --resolve`, still bound to usb0)
returned HTTP 200. A preceding domain probe using the system resolver timed out:
`resolv.conf` lists Ethernet DNS before phone DNS. USB WAN data and phone DNS
are validated; preferred-uplink DNS selection/failover remains a separate step.
