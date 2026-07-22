import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException

from backend.app.models.connection import ConnectionInput, ConnectionProfile

STATE_PATH = Path(os.environ.get("KRONOSKVM_STATE_PATH", "/var/lib/kronoskvm/state"))
CONNECTIONS_FILE = STATE_PATH / "connections.json"
_lock = threading.Lock()


def _read() -> list[ConnectionProfile]:
    try:
        payload = json.loads(CONNECTIONS_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=500, detail="Unable to read connection registry") from error
    return [ConnectionProfile.model_validate(item) for item in payload]


def _write(profiles: list[ConnectionProfile]) -> None:
    STATE_PATH.mkdir(parents=True, exist_ok=True)
    temporary = CONNECTIONS_FILE.with_suffix(".tmp")
    try:
        temporary.write_text(
            json.dumps([profile.model_dump() for profile in profiles], indent=2),
            encoding="utf-8",
        )
        temporary.replace(CONNECTIONS_FILE)
    except OSError as error:
        temporary.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Unable to save connection registry") from error


def list_connections() -> list[ConnectionProfile]:
    with _lock:
        return _read()


def create_connection(value: ConnectionInput) -> ConnectionProfile:
    profile = ConnectionProfile(
        **value.model_dump(),
        id=str(uuid.uuid4()),
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    with _lock:
        profiles = _read()
        profiles.append(profile)
        _write(profiles)
    return profile


def update_connection(profile_id: str, value: ConnectionInput) -> ConnectionProfile:
    with _lock:
        profiles = _read()
        for index, current in enumerate(profiles):
            if current.id == profile_id:
                updated = ConnectionProfile(
                    **value.model_dump(), id=current.id, created_at=current.created_at
                )
                profiles[index] = updated
                _write(profiles)
                return updated
    raise HTTPException(status_code=404, detail="Connection not found")


def delete_connection(profile_id: str) -> None:
    with _lock:
        profiles = _read()
        remaining = [profile for profile in profiles if profile.id != profile_id]
        if len(remaining) == len(profiles):
            raise HTTPException(status_code=404, detail="Connection not found")
        _write(remaining)
