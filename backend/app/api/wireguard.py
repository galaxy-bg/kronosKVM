"""Provisioning on the existing authenticated control plane."""

import json

from fastapi import APIRouter, HTTPException, Request

from backend.app.api.remote_assist import queue, read_status
from backend.app.security.auth import require_admin
from backend.app.services.wireguard_provisioning import registration_request, registration_response

router = APIRouter(prefix="/api/v1/wireguard", tags=["wireguard"])


@router.get("")
def status():
    live = read_status()
    # Explicit allowlist, even if a malformed host snapshot contains private fields.
    allowed = {"installed", "stale", "pending", "enabled", "autostart", "state",
               "last_handshake", "rx_bytes", "tx_bytes", "url", "last_result", "updated_at",
               "wireguard_installed", "configuration_present", "device_name", "vpn_ip"}
    value = {k: live[k] for k in allowed if k in live}
    profile = live.get("profile") or {}
    auto = live.get("auto_enrollment") or {}
    value["auto_enrollment"] = {k: auto[k] for k in (
        "ready", "state", "expires_at", "server",
    ) if k in auto}
    value["endpoint"] = profile.get("endpoint")
    value["allowed_ips"] = profile.get("allowed_ips")
    try:
        value["enrollment"] = registration_request(live.get("enrollment"))
    except ValueError:
        value["enrollment"] = None
    return value


@router.post("/identity", status_code=202)
def generate_identity(request: Request):
    require_admin(request)
    return queue({"action": "generate-identity"})


@router.put("/registration", status_code=202)
async def import_registration(request: Request):
    require_admin(request)
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 4096:
            raise HTTPException(413, "Registration metadata exceeds 4 KiB")
    try:
        registration = registration_response(json.loads(raw))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(400, "Invalid public registration metadata") from None
    return queue({"action": "register", "registration": registration})


@router.post("/enroll", status_code=202)
def auto_register(request: Request):
    require_admin(request)
    live = read_status()
    if live.get("enabled"):
        raise HTTPException(409, "Disconnect VPN before automatic registration")
    if not (live.get("auto_enrollment") or {}).get("ready"):
        raise HTTPException(409, "Administrator must authorize automatic registration first")
    return queue({"action": "auto-register"})


@router.post("/{action}", status_code=202)
def control(action: str, request: Request):
    require_admin(request)
    controls = {"connect": "enable", "disconnect": "disable", "restart": "restart",
                "enable-autostart": "boot-on", "disable-autostart": "boot-off"}
    if action not in controls:
        raise HTTPException(400, "Unsupported WireGuard action")
    if action in {"connect", "restart"} and not read_status().get("profile"):
        raise HTTPException(409, "Import an approved registration or existing VPN profile first")
    return queue({"action": controls[action]})
