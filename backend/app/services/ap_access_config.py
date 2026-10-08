"""Validated IPv4 policy shared by the API and restricted host helper."""

import ipaddress


def validate_policy(value):
    if not isinstance(value, dict) or type(value.get("enabled")) is not bool:
        raise ValueError("Enabled must be a boolean")
    networks = value.get("networks", [])
    if not isinstance(networks, list) or len(networks) > 16:
        raise ValueError("Specify at most 16 IPv4 networks")
    parsed = []
    for item in networks:
        if not isinstance(item, str) or len(item) > 32:
            raise ValueError("Invalid IPv4 network")
        network = ipaddress.IPv4Network(item, strict=True)
        if network.overlaps(ipaddress.IPv4Network("192.168.34.0/24")) and network.prefixlen:
            raise ValueError("The management subnet is protected")
        parsed.append(str(network))
    return {"enabled": value["enabled"], "networks": list(dict.fromkeys(parsed))}


def firewall_rules(policy):
    """Owned tables only; bridge ingress distinguishes Wi-Fi from Service USB."""
    policy = validate_policy(policy)
    allowed = ", ".join(policy["networks"] or ["0.0.0.0/0"])
    permit = ""
    nat = ""
    if policy["enabled"]:
        permit = (
            'iifname "br-recovery" oifname "eth0" meta nfproto ipv4 '
            'meta mark & 0x40000000 != 0 ip saddr 192.168.34.0/24 '
            f'ip daddr {{ {allowed} }} ct state {{ new, established, related }} '
            'ct mark set ct mark | 0x40000000 counter accept\n'
            'iifname "eth0" oifname "br-recovery" meta nfproto ipv4 '
            'ct mark & 0x40000000 != 0 ct state { established, related } counter accept\n'
        )
        nat = 'oifname "eth0" ip saddr 192.168.34.0/24 ct mark & 0x40000000 != 0 counter masquerade'
    return f'''table bridge kdx_ap_ingress {{
    chain ingress {{
        type filter hook prerouting priority -300; policy accept;
        meta mark set meta mark & 0xbfffffff
        iifname "wlan0" ether type ip meta mark set meta mark | 0x40000000
    }}
}}
table inet kdx_ap_access {{
    chain forward {{
        type filter hook forward priority -10; policy accept;
        {permit}
        iifname "br-recovery" oifname != "br-recovery" counter drop
        oifname "br-recovery" iifname != "br-recovery" counter drop
    }}
    chain nat {{
        type nat hook postrouting priority 100; policy accept;
        {nat}
    }}
}}
'''
