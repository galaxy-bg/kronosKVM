"""Public enrollment schema. Private key material never enters this protocol."""

import ipaddress
import re
import uuid

from backend.app.services.remote_assist_config import ProfileError, key, validate_profile

DEFAULT_ROUTES = "10.77.0.0/24"


def registration_request(value):
    if not isinstance(value, dict) or set(value) != {
        "version", "device_id", "hostname", "public_key", "request_id",
    } or value.get("version") != 1:
        raise ProfileError("Invalid public registration request")
    if not isinstance(value["device_id"], str) or not re.fullmatch(
        r"[0-9a-f]{16}", value["device_id"],
    ) or int(value["device_id"], 16) == 0:
        raise ProfileError("Invalid device serial")
    if not isinstance(value["hostname"], str) or not re.fullmatch(
        r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", value["hostname"],
    ):
        raise ProfileError("Invalid device hostname")
    key(value["public_key"], "Device public key")
    try:
        if str(uuid.UUID(value["request_id"])) != value["request_id"]:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise ProfileError("Invalid registration request identifier") from None
    return value.copy()


def registration_response(value):
    fields = {"version", "device_id", "hostname", "public_key", "request_id", "address",
              "server_public_key", "endpoint", "allowed_ips", "keepalive"}
    if not isinstance(value, dict) or set(value) != fields:
        raise ProfileError("Registration response must contain public metadata only")
    request = registration_request({k: value[k] for k in (
        "version", "device_id", "hostname", "public_key", "request_id",
    )})
    # Reuse strict endpoint, key, route, address and keepalive checks without a real secret.
    profile = validate_profile({"name": request["hostname"], "private_key": request["public_key"],
        "public_key": value["server_public_key"], "address": value["address"],
        "endpoint": value["endpoint"], "allowed_ips": value["allowed_ips"],
        "keepalive": value["keepalive"]})
    if ipaddress.IPv4Interface(profile["address"]).network.prefixlen != 32:
        raise ProfileError("Assigned device address must use /32")
    networks = [ipaddress.IPv4Network(x.strip()) for x in profile["allowed_ips"].split(",")]
    if not any(ipaddress.IPv4Interface(profile["address"]).ip in n for n in networks):
        raise ProfileError("Assigned address must belong to the permitted VPN routes")
    return {**request, "address": profile["address"], "server_public_key": profile["public_key"],
            "endpoint": profile["endpoint"], "allowed_ips": profile["allowed_ips"],
            "keepalive": profile["keepalive"]}
