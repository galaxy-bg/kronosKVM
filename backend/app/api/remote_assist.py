import fcntl
import json
import os
import time
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request

from backend.app.services.remote_assist_config import (
    ProfileError,
    parse_config,
    validate_profile,
)

router = APIRouter(prefix="/api/v1/remote-assist", tags=["remote-assist"])
STATE = Path(os.environ.get("KRONOSKVM_STATE_PATH", "/state"))


def read_status():
    try:
        data = json.loads((STATE / "remote-assist-status.json").read_text())
    except (OSError, ValueError):
        data = {"installed": False, "enabled": False, "state": "unavailable", "profile": None}
    data["stale"] = time.time() - data.get("updated_at", 0) > 30
    data["pending"] = (STATE / "remote-assist-request.json").exists()
    return data


@router.get("")
def status():
    return read_status()


def queue(payload):
    state = read_status()
    if not state.get("installed") or state["stale"]:
        raise HTTPException(503, "Remote Assist host helper is unavailable")
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / "remote-assist.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise HTTPException(409, "A Remote Assist action is in progress") from None
        target = STATE / "remote-assist-request.json"
        if target.exists():
            raise HTTPException(409, "A Remote Assist action is pending")
        payload["request_id"] = str(uuid.uuid4())
        temporary = STATE / f".remote-assist-{payload['request_id']}.tmp"
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w") as stream:
                json.dump(payload, stream)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    return {"accepted": True, "request_id": payload["request_id"]}


@router.put("/profile", status_code=202)
async def save_profile(request: Request):
    # Parse manually: validation errors must never echo submitted private keys.
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 20000:
            raise HTTPException(413, "Profile is too large")
    try:
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ProfileError("Invalid profile")
        profile = (
            parse_config(value["config"], value.get("name", ""))
            if "config" in value
            else validate_profile(value)
        )
    except (ValueError, TypeError, AttributeError) as error:
        detail = str(error) if isinstance(error, ProfileError) else "Invalid profile"
        raise HTTPException(400, detail) from None
    return queue({"action": "save", "profile": profile})


@router.post("/{action}", status_code=202)
async def control(action: Literal["enable", "disable", "boot-on", "boot-off"]):
    return queue({"action": action})
