import fcntl
import json
import os
import tempfile
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from backend.app.services.wifi_config import validate_wifi_update

router = APIRouter(prefix="/api/v1/network/wifi", tags=["network"])
STATE = Path(os.environ.get("KRONOSKVM_STATE_PATH", "/state"))


@router.get("")
def status():
    try:
        raw = json.loads((STATE / "wifi-status.json").read_text())
    except (OSError, ValueError):
        raw = {"installed": False, "state": "unavailable"}
    # Explicit allow-list: private configuration and request secrets are never returned.
    value = {key: raw[key] for key in (
        "installed", "ssid", "secured", "default_password", "state", "error", "updated_at",
        "request_id", "mode", "frequency_mhz", "channel", "width_mhz",
        "performance_available", "notice",
    ) if key in raw}
    value["stale"] = time.time() - value.get("updated_at", 0) > 60
    value["pending"] = (STATE / "wifi-request.json").exists()
    return value


@router.put("", status_code=202)
async def update(request: Request):
    body = bytearray()
    async for part in request.stream():
        body.extend(part)
        if len(body) > 1024:
            raise HTTPException(400, "Invalid Wi-Fi settings request")
    try:
        change = validate_wifi_update(json.loads(body))
    except (ValueError, TypeError, KeyError):
        raise HTTPException(
            400, "Use standard/performance mode or an 8–63 character ASCII password",
        ) from None
    live = status()
    if not live.get("installed") or live["stale"]:
        raise HTTPException(503, "Wi-Fi host helper is unavailable")
    with (STATE / "wifi.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise HTTPException(409, "A Wi-Fi action is in progress") from None
        target = STATE / "wifi-request.json"
        if target.exists():
            raise HTTPException(409, "A Wi-Fi action is pending")
        request_id = uuid.uuid4().hex
        fd, name = tempfile.mkstemp(prefix=".wifi-request-", dir=STATE)
        try:
            with os.fdopen(fd, "w") as stream:
                stream.write(json.dumps({**change, "request_id": request_id}))
            os.replace(name, target)
        finally:
            Path(name).unlink(missing_ok=True)
    return {"accepted": True, "request_id": request_id}
