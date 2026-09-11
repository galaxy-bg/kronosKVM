from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.app.logging import audit

router = APIRouter(prefix="/api/v1/session-logs", tags=["session-logs"])

STAGING_PATH = Path("/tmp/kronoskvm-session-logs")
MAX_LOG_BYTES = 5 * 1024 * 1024


class SessionLogInput(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    content: str
    started_at: Optional[datetime] = None


def _safe_filename(label: str, started_at: Optional[datetime]) -> str:
    slug = re.sub(r"[^a-z0-9]+", "", label.casefold())[:32] or "console"
    moment = started_at or datetime.now(timezone.utc)
    stamp = moment.astimezone(timezone.utc).strftime("%Y%m%d-%H%M%S")
    candidate = f"{slug}-{stamp}.txt"
    suffix = 2
    while (STAGING_PATH / candidate).exists():
        candidate = f"{slug}-{stamp}-{suffix}.txt"
        suffix += 1
    return candidate


def _entry(path: Path) -> dict:
    return {
        "filename": path.name,
        "size_bytes": path.stat().st_size,
        "created_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
        "download_url": f"/api/v1/session-logs/{path.name}",
    }


@router.get("")
def list_session_logs() -> dict:
    if not STAGING_PATH.exists():
        return {"entries": [], "temporary": True}
    entries = [_entry(path) for path in STAGING_PATH.glob("*.txt") if path.is_file()]
    entries.sort(key=lambda item: item["created_at"], reverse=True)
    return {"entries": entries, "temporary": True}


@router.post("", status_code=status.HTTP_201_CREATED)
def stage_session_log(value: SessionLogInput) -> dict:
    payload = value.content.encode("utf-8")
    if len(payload) > MAX_LOG_BYTES:
        raise HTTPException(status_code=413, detail="Session log exceeds the 5 MiB limit")
    STAGING_PATH.mkdir(mode=0o700, parents=True, exist_ok=True)
    filename = _safe_filename(value.label, value.started_at)
    path = STAGING_PATH / filename
    path.write_bytes(payload)
    audit("session.log.staged", session_log_file=filename, size_bytes=len(payload))
    return _entry(path)


@router.get("/{filename}")
def download_session_log(filename: str) -> FileResponse:
    if Path(filename).name != filename or not filename.endswith(".txt"):
        raise HTTPException(status_code=400, detail="Invalid session log name")
    path = STAGING_PATH / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Session log not found")
    return FileResponse(path, filename=filename, media_type="text/plain; charset=utf-8")
