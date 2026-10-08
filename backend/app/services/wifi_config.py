"""Wi-Fi passphrase rules shared by the API and root provisioning helper."""

import hashlib

from backend.app.services.device_identity import identity_from_serial


def default_password(serial: str) -> str:
    serial = identity_from_serial(serial)["serial"]
    return f"KDX@{serial[-8:]}!"


def validate_password(value) -> str:
    if not isinstance(value, str) or not 8 <= len(value) <= 63:
        raise ValueError("Wi-Fi password must contain 8–63 printable ASCII characters")
    if any(ord(char) < 32 or ord(char) > 126 for char in value):
        raise ValueError("Wi-Fi password must contain 8–63 printable ASCII characters")
    return value


def network_psk(password: str, ssid: str) -> str:
    return hashlib.pbkdf2_hmac("sha1", password.encode("ascii"), ssid.encode(), 4096, 32).hex()


def validate_wifi_update(value) -> dict:
    if not isinstance(value, dict) or set(value) not in ({"password"}, {"mode"}):
        raise ValueError("Submit a Wi-Fi password or mode")
    if "password" in value:
        return {"password": validate_password(value["password"])}
    if value["mode"] not in ("standard", "performance"):
        raise ValueError("Wi-Fi mode must be standard or performance")
    return {"mode": value["mode"]}
