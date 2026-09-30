# Appliance hostname

All appliances use the fixed system hostname `kdx-infrabox` and Recovery access
name `kdx-infrabox.local`. Do not add numeric suffixes. Appliances serve separate
Recovery networks; serial numbers/device IDs remain their unique identifiers.

Bootstrap sets the system hostname and local hosts entry, and preserves it on
cloud-init systems. Recovery dnsmasq configuration advertises the new DHCP domain
and resolves `kdx-infrabox.local` to `192.168.34.100`. Existing DHCP clients may
retain the old search domain until their lease renews.

Applied the Recovery DNS/DHCP change to 192.168.1.112 on 2026-09-30. Its system
hostname was already correct. DNS configuration validation and a direct Recovery
DNS query passed; HTTPS health with the new Host name passed. No reboot or KVM
restart was required. Backup: `/var/backups/kronoskvm/hostname-20260930`.
Future certificates include the new FQDN; existing self-signed certificates are
not rotated by this change. Other physical appliances have not been contacted.
