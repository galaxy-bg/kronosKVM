from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class SystemConfig(BaseModel):
    hostname: str = "kronoskvm"
    timezone: str = "Europe/Istanbul"
    data_directory: Path = Path("/var/lib/kronoskvm")
    runtime_directory: Path = Path("/run/kronoskvm")
    log_directory: Path = Path("/var/log/kronoskvm")


class NetworkConfig(BaseModel):
    management_interface: str | None = None
    service_interface: str | None = None
    management_address: str = "192.168.31.145"
    web_bind_address: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)


class AppConfig(BaseModel):
    system: SystemConfig = SystemConfig()
    network: NetworkConfig = NetworkConfig()


def load_config(path: Path) -> AppConfig:
    if not path.exists():
        return AppConfig()
    with path.open(encoding="utf-8") as config_file:
        raw: dict[str, Any] = yaml.safe_load(config_file) or {}
    return AppConfig.model_validate(raw)
