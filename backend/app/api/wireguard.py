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
    value["central_vpn"] = {k: (live.get("central_vpn") or {}).get(k) for k in ("status", "updated_at", "error")}
    value["endpoint"] = profile.get("endpoint")
    value["allowed_ips"] = profile.get("allowed_ips")
    try:
        value["enrollment"] = registration_request(live.get("enrollment"))
    except ValueError:
        value["enrollment"] = None
    return value


@router.delete("", status_code=202)
def delete_vpn(request: Request):
    require_admin(request)
    return queue({"action":"delete-profile"})


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


@router.post("/enroll")
def legacy_restore_removed(request: Request):
    require_admin(request)
    raise HTTPException(410, "Restore was removed; request a fresh VPN setup")


async def setup_input(request):
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 4096:
            raise HTTPException(413, "Setup request is too large")
    try:
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError
        return value
    except (ValueError, TypeError):
        raise HTTPException(400, "Invalid setup request") from None


@router.post("/central-register", status_code=202)
def central_register(request: Request):
    require_admin(request)
    return queue({"action": "central-register"})


@router.post("/server-check")
@router.post("/quick-register")
def password_setup_removed(request: Request):
    require_admin(request)
    raise HTTPException(410, "Password-based setup was removed; request VPN access from the central dashboard")


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
