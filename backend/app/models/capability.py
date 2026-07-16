from enum import StrEnum

from pydantic import BaseModel


class HardwareStatus(StrEnum):
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
    detail: str | None = None
