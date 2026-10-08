import fcntl
import json
import os
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.services.ap_access_config import validate_policy

router = APIRouter(prefix="/api/v1/network/ap-access", tags=["network"])
STATE = Path(os.environ.get("KRONOSKVM_STATE_PATH", "/state"))


class PolicyInput(BaseModel):
    enabled: bool
    networks: list[str] = Field(default_factory=list, max_length=16)


@router.get("")
def status():
    try:
        value = json.loads((STATE / "ap-access-status.json").read_text())
    except (OSError, ValueError):
        value = {"installed": False, "enabled": False, "networks": [], "state": "unavailable"}
    value["stale"] = time.time() - value.get("updated_at", 0) > 60
    value["pending"] = (STATE / "ap-access-request.json").exists()
    return value


@router.put("", status_code=202)
def update(value: PolicyInput):
    try:
        policy = validate_policy(value.model_dump())
    except ValueError as error:
        raise HTTPException(400, str(error)) from None
    live = status()
    if not live.get("installed") or live["stale"]:
        raise HTTPException(503, "AP access host helper is unavailable")
    with (STATE / "ap-access.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise HTTPException(409, "An AP access action is in progress") from None
        target = STATE / "ap-access-request.json"
        if target.exists():
            raise HTTPException(409, "An AP access action is pending")
        temporary = STATE / ".ap-access-request.tmp"
        temporary.write_text(json.dumps(policy))
        temporary.replace(target)
    return {"accepted": True}
