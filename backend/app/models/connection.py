from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

ConnectionType = Literal["ssh", "telnet", "rdp", "vnc", "web"]


class ConnectionInput(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    type: ConnectionType
    host: str = Field(min_length=1, max_length=253)
    port: int = Field(ge=1, le=65535)
    username: Optional[str] = Field(default=None, max_length=64)
    path: str = Field(default="/", max_length=512)

    @field_validator("name", "host", "username", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("host")
    @classmethod
    def validate_host(cls, value: str) -> str:
        if any(character in value for character in "/\\?#@ "):
            raise ValueError("Host must be an IP address or hostname")
        return value

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return value if value.startswith("/") else f"/{value}"


class ConnectionProfile(ConnectionInput):
    id: str
    created_at: str
