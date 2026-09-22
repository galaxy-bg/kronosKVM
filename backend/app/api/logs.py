from __future__ import annotations

import json
import os
from collections import deque
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/v1/logs", tags=["logs"])

LOG_PATH = Path(os.environ.get("KRONOSKVM_LOG_PATH", "/var/log/kronoskvm/application.jsonl"))


@router.get("")
def get_logs(
    limit: int = Query(default=200, ge=1, le=1000),
    level: Optional[str] = Query(default=None),
    event: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None, max_length=200),
) -> dict:
    if not LOG_PATH.is_file():
        return {"entries": [], "count": 0}

    candidates: deque[str] = deque(maxlen=5000)
    with LOG_PATH.open(encoding="utf-8", errors="replace") as log_file:
        for line in log_file:
            candidates.append(line)

    normalized_level = level.upper() if level else None
    normalized_search = search.casefold() if search else None
    entries: list[dict] = []
    for line in reversed(candidates):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if normalized_level and entry.get("level") != normalized_level:
            continue
        if event and entry.get("event") != event:
            continue
        if normalized_search and normalized_search not in line.casefold():
            continue
        entries.append(entry)
        if len(entries) >= limit:
            break
    return {"entries": entries, "count": len(entries)}
