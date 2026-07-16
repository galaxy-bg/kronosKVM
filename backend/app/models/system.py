from typing import Optional

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    version: str
    hostname: str


class SystemInfo(BaseModel):
    hostname: str
    model: str
    architecture: str
    kernel: str
    uptime_seconds: int
    load_average: list[float]


class NetworkInterface(BaseModel):
    name: str
    state: str
    mac_address: Optional[str] = None
    addresses: list[str]


class NetworkInfo(BaseModel):
    interfaces: list[NetworkInterface]


class StorageInfo(BaseModel):
    root_total_bytes: int
    root_used_bytes: int
    root_free_bytes: int
    root_percent_used: float


class ServiceState(BaseModel):
    name: str
    state: str


class ServicesInfo(BaseModel):
    services: list[ServiceState]


class TemperatureInfo(BaseModel):
    status: str
    celsius: Optional[float] = None
