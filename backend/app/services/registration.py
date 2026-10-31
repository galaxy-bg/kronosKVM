"""Read a sanitized, read-only host-agent snapshot; never mount its private identity."""

import json
import os
import time
from pathlib import Path

from backend.app.services.device_identity import read_identity

FIELDS = {
    "serial",
    "installation_id",
    "device_id",
    "license_id",
    "checked_at",
    "authorization_expires_at",
    "server_url",
    "authorized",
    "status",
    "mode",
    "transport",
    "error",
}
STATES = {
    "PENDING",
    "ACTIVATION_REQUIRED",
    "ACTIVE",
    "SUSPENDED",
    "REVOKED",
    "EXPIRED",
    "HARDWARE_MISMATCH",
    "DENIED",
    "UNAVAILABLE",
}


def read_registration_status():
    path = Path(os.environ.get("KRONOSKVM_REGISTRATION_STATUS_PATH", "/registration/status.json"))
    try:
        if path.stat().st_size > 16384:
            raise ValueError("Oversized status")
        value = json.loads(path.read_text())
        if not isinstance(value, dict) or value.get("status") not in STATES:
            raise ValueError("Invalid status")
        result = {k: v for k, v in value.items() if k in FIELDS}
        checked = result.get("checked_at")
        if isinstance(checked, bool) or not isinstance(checked, (int, float)):
            raise ValueError("Invalid timestamp")
        tick = time.time()
        result["installed"] = True
        result["stale"] = not 0 <= tick - checked <= 900
        serial = read_identity()["serial"].upper()
        if serial != str(result.get("serial", "")).upper():
            result.update(authorized=False, status="HARDWARE_MISMATCH", error="HARDWARE_MISMATCH")
        elif result["stale"]:
            result.update(authorized=False, status="UNAVAILABLE", error="STATUS_STALE")
        elif result.get("authorized") is True:
            expiry = result.get("authorization_expires_at")
            if (
                result["status"] != "ACTIVE"
                or isinstance(expiry, bool)
                or not isinstance(expiry, (int, float))
                or expiry <= tick
            ):
                result.update(authorized=False, status="UNAVAILABLE", error="AUTHORIZATION_EXPIRED")
        else:
            result["authorized"] = False
        return result
    except FileNotFoundError:
        return {"installed": False, "status": "NOT_CONFIGURED", "authorized": False, "stale": True}
    except (OSError, ValueError, TypeError):
        return {
            "installed": True,
            "status": "UNAVAILABLE",
            "authorized": False,
            "stale": True,
            "error": "STATUS_UNAVAILABLE",
        }
