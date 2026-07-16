from enum import Enum
from typing import Optional

from pydantic import BaseModel


class HardwareStatus(str, Enum):
    READY = "ready"
    RUNNING = "running"
    DISABLED = "disabled"
    NOT_DETECTED = "not_detected"
    WAITING_FOR_HARDWARE = "waiting_for_hardware"
    UNSUPPORTED = "unsupported"
    ERROR = "error"


class Capability(BaseModel):
    name: str
    status: HardwareStatus
    detail: Optional[str] = None
