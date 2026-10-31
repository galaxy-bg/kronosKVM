"""Provisioning on the existing authenticated control plane."""

import asyncio
import json

from fastapi import APIRouter, HTTPException, Request

from backend.app.api.remote_assist import queue, read_status
from backend.app.security.auth import require_admin
from backend.app.services import wireguard_quick
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


@router.post("/server-check")
async def check_server(request: Request):
    require_admin(request)
    value = await setup_input(request)
    try:
        key = await wireguard_quick.server_key(value)
        return {"fingerprint": key.get_fingerprint()}
    except ValueError as error:
        raise HTTPException(400, str(error)) from None


@router.post("/quick-register", status_code=202)
async def quick_register(request: Request):
    require_admin(request)
    # Per-process single setup worker; the host queue has its own cross-process lock.
    lock = getattr(request.app.state, "vpn_setup_lock", None)
    if lock is None:
        lock = request.app.state.vpn_setup_lock = asyncio.Lock()
    if lock.locked():
        raise HTTPException(409, "VPN setup is already in progress")
    async with lock:
        live = read_status()
        if live.get("enabled") or live.get("pending"):
            raise HTTPException(409, "Disconnect VPN and wait for pending actions before setup")
        if live.get("stale") or not live.get("installed"):
            raise HTTPException(503, "VPN host module is unavailable")
        if not live.get("enrollment"):
            raise HTTPException(409, "Create the device identity before server setup")
        value = await setup_input(request)
        try:
            response = await wireguard_quick.register(value, live["enrollment"])
        except ValueError as error:
            raise HTTPException(400, str(error)) from None
        finally:
            value.clear()  # No credential enters the queue, status snapshot or configuration.
        return queue({"action": "register-connect", "registration": response})


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
