"""Strict, dependency-free WireGuard profile validation shared with the host helper."""

import base64
import configparser
import ipaddress
import re

PRIVATE_NETWORKS = tuple(
    ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)


class ProfileError(ValueError):
    pass


def key(value, label):
    try:
        if len(base64.b64decode(value, validate=True)) != 32:
            raise ValueError
    except (ValueError, TypeError):
        raise ProfileError(f"{label} must be a base64 WireGuard key") from None
    return value


def validate_profile(value):
    if not isinstance(value, dict):
        raise ProfileError("Invalid profile")
    name = value.get("name", "").strip()
    if not name or len(name) > 80 or any(ord(c) < 32 for c in name):
        raise ProfileError("Profile name is required (maximum 80 characters)")
    try:
        address = ipaddress.IPv4Interface(value.get("address", ""))
        if not any(address.ip in n for n in PRIVATE_NETWORKS):
            raise ValueError
        routes = [
            ipaddress.IPv4Network(x.strip(), strict=False)
            for x in value.get("allowed_ips", "").split(",")
        ]
        if (
            not routes
            or len(routes) > 16
            or any(not any(n.subnet_of(private) for private in PRIVATE_NETWORKS) for n in routes)
        ):
            raise ValueError
    except (ValueError, TypeError):
        raise ProfileError(
            "Use a private IPv4 VPN address and specific private IPv4 peer networks; "
            "full-tunnel and IPv6 profiles are not supported in this version"
        ) from None
    endpoint = value.get("endpoint", "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,252}:[0-9]{1,5}", endpoint):
        raise ProfileError("Endpoint must be a hostname or IPv4 address followed by :port")
    if not 1 <= int(endpoint.rsplit(":", 1)[1]) <= 65535:
        raise ProfileError("Endpoint port is invalid")
    try:
        keepalive = int(value.get("keepalive", 25))
        if not 0 <= keepalive <= 65535:
            raise ValueError
    except (ValueError, TypeError):
        raise ProfileError("Keepalive must be between 0 and 65535 seconds") from None
    psk = value.get("preshared_key", "").strip()
    return {
        "name": name,
        "address": str(address),
        "endpoint": endpoint,
        "allowed_ips": ", ".join(map(str, routes)),
        "keepalive": keepalive,
        "private_key": key(value.get("private_key", "").strip(), "Private key"),
        "public_key": key(value.get("public_key", "").strip(), "Server public key"),
        "preshared_key": key(psk, "Preshared key") if psk else "",
    }


def parse_config(text, name):
    if not isinstance(text, str) or len(text) > 16384:
        raise ProfileError("Configuration must be smaller than 16 KiB")
    parser = configparser.ConfigParser(
        interpolation=None, strict=True, inline_comment_prefixes=("#", ";")
    )
    try:
        parser.read_string(text)
    except configparser.Error:
        raise ProfileError("Invalid WireGuard configuration or duplicate sections") from None
    if parser.defaults() or set(parser.sections()) != {"Interface", "Peer"}:
        raise ProfileError("Configuration must contain one Interface and one Peer")
    allowed = {
        "Interface": {"privatekey", "address"},
        "Peer": {"publickey", "presharedkey", "endpoint", "allowedips", "persistentkeepalive"},
    }
    for section in parser.sections():
        if set(parser[section]) - allowed[section]:
            raise ProfileError(
                "Only VPN keys, Address, Endpoint, AllowedIPs and "
                "PersistentKeepalive are supported; remove DNS, hooks and other options"
            )
    interface, peer = parser["Interface"], parser["Peer"]
    return validate_profile(
        {
            "name": name,
            "address": interface.get("address", ""),
            "private_key": interface.get("privatekey", ""),
            "public_key": peer.get("publickey", ""),
            "preshared_key": peer.get("presharedkey", ""),
            "endpoint": peer.get("endpoint", ""),
            "allowed_ips": peer.get("allowedips", ""),
            "keepalive": peer.get("persistentkeepalive", "25"),
        }
    )


def public_profile(profile):
    return {k: v for k, v in profile.items() if k not in {"private_key", "preshared_key"}}
