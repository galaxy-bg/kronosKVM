# Wi-Fi access to customer networks

Settings → **AP access to customer network** controls IPv4 forwarding from
Wi-Fi laptops through the customer Ethernet interface (`eth0`). Fresh
installations default to disabled. The saved choice survives reboot. Existing
appliance-originated SSH/Telnet/RDP/VNC connections are independent of this setting.

Enable the checkbox and save. Optionally list up to 16 canonical IPv4 CIDRs,
such as `192.168.1.0/24, 10.20.0.0/16`. Blank means all destinations routed
through Ethernet, including internet when the customer's uplink permits it.
IPv6, VPN and USB-WAN forwarding are not enabled by this feature.

Reconnect laptop Wi-Fi after enabling so DHCP supplies gateway/DNS
`192.168.34.100`. Ethernet DNS resolution depends on the host's upstream resolver.
Enabling the option does not bypass customer ACLs or install missing customer
routes. Multiple laptops can use independent sessions through source NAT.

## Host implementation

Run `sudo bash /opt/kronoskvm/scripts/install-ap-access.sh` after installing the
application files. Requires the current `br-recovery`/`wlan0`/`eth0` topology,
nftables and dnsmasq. Root-owned `/etc/kronoskvm/ap-access.json` stores policy;
the authenticated API queues validated requests in the shared state directory.
The API container receives no firewall/root access.

The helper owns only `bridge kdx_ap_ingress` and `inet kdx_ap_access`. Bridge
ingress marks identify Wi-Fi traffic separately from Service USB traffic even
though both use `br-recovery`. Only eligible Wi-Fi flows and established replies
are permitted. Recovery-port forwarding and new inbound customer connections
are blocked. Disabling removes the permit/NAT rules, including permission for
existing sessions. Same-bridge layer-2 communication and local box access remain.

Global IPv4 forwarding is enabled when needed; disabling leaves that global
switch alone for other host services. The owned firewall rules enforce the AP
disabled state. This implementation must not be combined with unrelated flow
offload rules that bypass its forwarding chain. Other firewall policies can
still reject traffic. Runtime status refreshes every 20 seconds.

## Deployment and validation — 2026-10-08

Installed on the second appliance, `192.168.1.107`, and subsequently on the
first appliance, `192.168.31.185`. See the
[first-box update record](first-appliance-update-20261008.md) for its disabled
initial policy and preserved local DNS. No OS reboot/update was performed.

- Application/private-state backup:
  `/var/backups/kronoskvm/pre-ap-access-update-20261008.NnuSNL`.
- Original DNS configuration backup:
  `/var/backups/kronoskvm/ap-access-install.wiDcim/dnsmasq.d`.
- Previous images: `kronoskvm-api:pre-ap-access-update-20261008` and
  `kronoskvm-web:pre-ap-access-update-20261008`.
- New images: `kronoskvm-api:ap-access-update-20261008` and
  `kronoskvm-web:ap-access-update-20261008`, also tagged `:dev`.

172 unit/asset tests and lint passed. A temporary router namespace on the actual
ARM64 host validated disabled routing even with global forwarding on, two Wi-Fi
source IPs, NAT, Service-port exclusion, CIDR filtering, unsolicited inbound
blocking, unrestricted Ethernet destinations and disabling. Test namespaces and
target processes were removed afterward.

Live Chrome validated Settings, default-off initialization, restricted enable,
disable, desktop/mobile layout and no page errors. After this test, a subsequent
request enabled unrestricted access; observed live firewall counters confirmed
Wi-Fi forwarding and reply traffic. That active setting was preserved rather
than interrupting the operator's connection. Fresh-install defaults remain off.

For rollback, first disable access in Settings. Stop/disable the AP-access boot,
path and timer units; delete only the two owned nft tables; restore the original
dnsmasq configuration and restart dnsmasq. Restore the application archive and
previous API/web image tags, then reload `kronoskvm-containers.service`. On this
device global IPv4 forwarding was originally zero; restore that value only if
no other service now requires it. Never flush unrelated firewall tables or
restore private credentials merely to roll back application code.

References: [nftables official manual](https://netfilter.org/projects/nftables/manpage.html),
[dnsmasq DHCP options](https://dnsmasq.org/docs/dnsmasq-man.html).
