import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from backend.app.models import SerialLock, SerialProfile


def load_profiles(path: Path = Path("/etc/kronoskvm/serial-profiles.yaml")) -> list[SerialProfile]:
    fallback = {
        "default": {
            "baud_rate": 9600,
            "data_bits": 8,
            "parity": "none",
            "stop_bits": 1,
            "flow_control": "none",
        },
        "fast": {
            "baud_rate": 115200,
            "data_bits": 8,
            "parity": "none",
            "stop_bits": 1,
            "flow_control": "none",
        },
        "medium": {
            "baud_rate": 38400,
            "data_bits": 8,
            "parity": "none",
            "stop_bits": 1,
            "flow_control": "none",
        },
        "legacy": {
            "baud_rate": 19200,
            "data_bits": 8,
            "parity": "none",
            "stop_bits": 1,
            "flow_control": "none",
        },
    }
    try:
        with path.open(encoding="utf-8") as profile_file:
            raw = yaml.safe_load(profile_file) or {}
        profiles = raw.get("profiles", fallback)
    except OSError:
        profiles = fallback
    return [
        SerialProfile(name=name, **values)
        for name, values in sorted(profiles.items())
    ]


class SerialLockRegistry:
    def __init__(self) -> None:
        self._mutex = threading.Lock()
        self._locks: dict[str, SerialLock] = {}

    def acquire(self, device: str, owner: str) -> Optional[SerialLock]:
        with self._mutex:
            if device in self._locks:
                return None
            lock = SerialLock(
                device=device,
                owner=owner,
                token=str(uuid.uuid4()),
                acquired_at=datetime.now(timezone.utc).isoformat(),
            )
            self._locks[device] = lock
            return lock

    def release(self, device: str, token: str) -> bool:
        with self._mutex:
            lock = self._locks.get(device)
            if lock is None or lock.token != token:
                return False
            del self._locks[device]
            return True

    def list(self) -> list[SerialLock]:
        with self._mutex:
            return list(self._locks.values())


serial_locks = SerialLockRegistry()
