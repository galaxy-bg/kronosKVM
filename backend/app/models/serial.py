from typing import Optional

from pydantic import BaseModel, Field


class SerialProfile(BaseModel):
    name: str
    baud_rate: int = Field(ge=50, le=4_000_000)
    data_bits: int = Field(ge=5, le=8)
    parity: str
    stop_bits: float
    flow_control: str


class SerialDevice(BaseModel):
    device: str
    stable_path: Optional[str] = None
    vendor_id: Optional[str] = None
    product_id: Optional[str] = None
    serial_number: Optional[str] = None
    driver: Optional[str] = None
    suggested_profile: str = "default"


class SerialInventory(BaseModel):
    devices: list[SerialDevice]
    profiles: list[SerialProfile]
    tcp_exposure_enabled: bool = False


class SerialLockRequest(BaseModel):
    device: str
    owner: str = Field(min_length=1, max_length=128)


class SerialLock(BaseModel):
    device: str
    owner: str
    token: str
    acquired_at: str


class SerialUnlockRequest(BaseModel):
    token: str
