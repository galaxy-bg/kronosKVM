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

## Dual-uplink investigation — 2026-11-01

On the real appliance, Samsung RNDIS tethering on the Storage/WAN port created
`usb0` with `10.107.147.39/24`, gateway/DNS `10.107.147.224`. Interface-bound HTTPS
to an independent public endpoint and the Registration Server both returned 200.
A DNS query sent directly through USB to the phone resolver succeeded.

Ethernet's DHCP default route (metric 101) takes priority over USB (600). This is
link/route-based fallback: an Ethernet gateway without internet can still win.
No automatic internet-health failover has been installed by this investigation.

A temporary route for the public VPN endpoint forced WireGuard through USB.
Packet-header observation on USB confirmed outbound UDP packets from its DHCP
address to `185.251.66.26:51820`, but no replies arrived and VPN pings failed.
Concurrent packet-header observation on the VPN VM saw Ethernet-side traffic but
no mobile-side traffic during the test. The phone's observed HTTPS egress address
was `176.55.25.50`; carrier egress addresses may differ for UDP and may change.
This isolates an additional fault on the mobile-to-VPN path, without proving
whether it is the carrier, WAN firewall policy or VIP/DNAT. Inspect FortiGate
WAN-side captures and policy/VIP matches before changing server or device routing.

All temporary endpoint routes were removed. Ethernet VPN pings succeeded again.
No WireGuard keys, peer registrations, firewall policies or persistent route
priorities were changed. The user requested continued focus on the USB/device path before any WAN changes.


### Follow-up

Normal unbound host HTTPS (both IP literal and hostname) succeeded after temporarily
removing only the Ethernet default route; direct USB queries to both public DNS
resolvers also succeeded. A short source-port-reset VPN trial appeared successful,
but longer controlled tests did not reproduce reliable USB VPN replies. Socket
refresh alone and a fresh NetworkManager VPN connection did not resolve it.
The experimental automatic UDP-socket-refresh code was rolled back; no VPN fix
is claimed. Temporary default/endpoint routes and listener-port tests were restored.

The AP forwarding policy was disabled. A laptop-sharing extension was temporarily
implemented, but the user clarified that the AP should remain a management-only
network. Its source changes have been removed; device rollback is pending restored
management access. The actual requested behavior is host internet/VPN through USB,
with the AP used only to manage the box.

The API's Python 3.9 compatibility issue during the temporary extension was fixed
and health/auth-session JSON checked successfully before management access was lost.
A reboot during testing left VPN disabled because autostart was false; it was
explicitly enabled again without changing the saved autostart preference.


## Real USB-only comparison — 2026-11-02

Operator unplugged Ethernet and connected the management laptop to the AP
(`192.168.34.174` → box `192.168.34.100`). The only host default route was USB
`10.107.147.224`; normal host HTTPS/DNS worked. After a reboot the saved
`autostart: false` left VPN off; it was explicitly enabled, preserving that preference.
Initial mobile-data egress `176.55.25.50` sent valid WireGuard initiation packets
without a reply. Client/server public keys and addresses matched, no PSK mismatch
was present, and clock synchronization was confirmed. Packet header checks found
valid IPv4/UDP checksums and MAC1; temporary client source-port, DSCP and TTL
experiments were inconclusive and were removed/restored. The VPN server was only
observed; no peer/route/firewall configuration was changed.

Later, while Ethernet remained unplugged, the phone egress changed to home Wi-Fi
`149.0.147.146`. The box then established a fresh handshake through USB and all
five VPN pings succeeded. The device's original listener port was still restored.
This is not yet proof of a mobile-data fix. A controlled phone Wi-Fi-off, fresh VPN
session comparison is pending the operator's physical network change.

The CLI internet probe previously hard-bound `eth0`, giving a false negative on
USB-only operation. `scripts/kronoskvm` now discovers and probes the actual IPv4
outgoing interface; both installed copies were updated and reported
`Internet reachability: reachable via usb0`. Backup is
`/var/backups/kronoskvm/usb-uplink-status-20261102` on the appliance.

AP sharing extensions were removed from local source after scope clarification;
the live test appliance still has the temporary sharing extension so the sole
AP management/internet path is preserved during diagnosis. Restore the AP-only
scope once an alternate management/internet path is available. Do not publish the
source rollback as if live AP rollback had already completed.

### Controlled AP/laptop comparison — 2026-11-02

Read-only routing checks found the appliance endpoint route using `usb0` and the
phone gateway; Ethernet was absent. The AP policy rule applies to marked AP
sources, not the appliance's own WireGuard source. Keepalive was already 25s.

With the operator confirming home Wi-Fi upstream, simultaneous short tests found
60% VPN ping loss on both the appliance and the laptop's separate `10.77.0.12`
peer. Appliance public-IP ping loss was 53%, while the USB phone gateway had
0% loss (about 1ms). Thus this loss was not exclusive to appliance VPN traffic.
Eight HTTPS probes succeeded, some taking up to 1.8s; ICMP alone does not identify
the cause of that upstream loss.

After the operator switched the phone to mobile data, HTTPS confirmed mobile
egress and both appliance and laptop VPN tests initially passed 10/10. Restarting
only `KDX-Remote-Assist` allocated UDP source port `53607`; the appliance then
received no handshake response and lost 20/20 VPN pings. Returning only its
runtime listen port to the previously working `55409` produced a fresh handshake
and 8/8 successful pings. A subsequent 30-ping test passed without loss, averaging
26.8ms. This implicates UDP flow/NAT state or port-dependent
handling, but does not locate it in the phone, carrier or server ingress, nor
prove that an arbitrary port change is a durable fix. No permanent profile,
route, AP, firewall, key or server configuration was changed. The appliance VPN
was left active on its original runtime port `55409`; its saved automatic port
selection remains unchanged. A phone reconnect/reboot can invalidate this state.

### Reboot/reconnect reproduction — 2026-11-02

After the operator's next restart, the appliance selected runtime port `42025`
and again had no handshake or received bytes. Its endpoint route still used USB.
Returning to `55409` now also failed (12/12 lost). Brief runtime trials using
`51820`, `443` and an automatically selected port did not establish a handshake;
these short trials are not evidence that those ports can never work.

The operator also restarted the laptop's separate VPN while remaining on mobile
data. Laptop VPN pings then passed 8/8, while the appliance still received no
WireGuard packets. USB header observation confirmed outbound appliance handshake
initiations with no corresponding inbound response, alongside bidirectional
laptop WireGuard traffic on the same USB uplink. A captured appliance initiation
passed IPv4 checksum, UDP checksum and server-key MAC1 validation. NTP was
synchronized and its clock matched the management laptop. USB TX checksum
offloading was already off; no offload setting was changed.

This rules out the earlier port reset as a reliable fix. It does not establish
where the appliance flow is lost or rejected. Server-side concurrent observation
is needed to distinguish non-arrival from server rejection or lost replies.
The original runtime port `42025` was restored, automatic profile port selection
remained `0`, and VPN remained enabled but without a handshake. No persistent
device or server setting was changed during this follow-up.

### Concurrent VPN-server observation — 2026-11-02

Using the laptop's working tunnel, read-only SSH access to `10.77.0.1` confirmed
the existing appliance peer and correct server public key/listen port. During
concurrent appliance ping/handshake attempts, `ens34` packet observation showed
the laptop's bidirectional UDP flow, but no arriving appliance initiation. The
server retained an old appliance endpoint/handshake and occasionally sent its
own initiation toward that old endpoint. Its route to the mobile public IP used
the expected upstream gateway. No server configuration was changed.

USB observation distinguished the laptop's outgoing DSCP CS0/TTL 63 transport
packets from the appliance's DSCP AF41 (`0x88`)/TTL 64 initiation packets. A
temporary, endpoint-specific appliance output rule cleared DSCP; its counter
matched two outgoing initiations, but all 12 VPN pings still failed. The rule
and its temporary table were removed. This trial does not prove that DSCP
cannot affect other/new flows, but it did not resolve the observed failure.

Current evidence places loss between the observed appliance USB egress and the
VPN VM ingress; it cannot distinguish phone handling, carrier transit or the
public gateway/VIP path. WAN-side gateway capture is the next observation point,
rather than an unproven persistent device routing or port change.

### USB 3 / container network audit — 2026-11-02

Live `lsusb -t` confirmed the Samsung RNDIS interface at `5000M` on physical
path `2-1`. Twenty USB gateway pings passed without loss, averaging 1.86ms.
The interface's single cumulative RX error did not increase during this check;
TX errors/drops were zero. The USB qdisc had no drops or backlog and no ingress
or egress TC filter was installed. Boot logs showed phone mode re-enumeration,
but no subsequent repeating USB reset pattern. Firmware throttling flags were 0.
The negotiated bus speed is not a measured internet-throughput result.

API, web and guacd were healthy and used exactly the host's network namespace
(verified through `/proc` namespace IDs). Docker had only host/none networks;
its bridge, iptables management and masquerading were disabled. No separate
container route or Docker NAT is required for the host-managed `wg-kdx` tunnel.
Host API/web probes returned HTTP 200, and API-container localhost health and
external HTTPS both returned 200.

The endpoint route used `usb0`, while `10.77.0.1` used `wg-kdx`. The AP-only
marked policy rule did not select host-originated traffic. Both nftables and
legacy iptables were checked: only the existing AP bridge/forwarding/NAT rules
were present, with no host INPUT/OUTPUT filtering or Docker chains. IPv4
forwarding was enabled for live AP sharing; this was not changed. No USB,
container, firewall or routing settings were modified. The missing appliance
VPN handshake remained unresolved; service access over that tunnel cannot be
validated until it establishes.

### Requested MTU 1280 comparison — 2026-11-02

With HTTPS confirming mobile egress, the existing endpoint `185.251.66.26:51820`
and keepalive 25s were retained. Runtime `wg-kdx` MTU was changed from 1420 to
1280, without restarting the tunnel or changing its source port. Baseline 1420
lost 5/5 pings; MTU 1280 lost 20/20, with no handshake and zero received bytes.
The original MTU 1420 was restored and a further 5/5 pings were lost. This MTU
change did not resolve the observed handshake failure. No persistent profile
setting was changed.
