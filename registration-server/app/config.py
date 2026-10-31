from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="KDX_", env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://kdx_registration@127.0.0.1/kdx_registration"
    signing_key: str = "/etc/kdx-registration/signing.pem"
    audience: str = "kdx-infrabox-registration"
    offline_grace_seconds: int = Field(default=86400, ge=60, le=604800)
    challenge_seconds: int = Field(default=120, ge=15, le=300)
    device_session_seconds: int = Field(default=300, ge=30, le=900)
    rate_per_minute: int = Field(default=120, ge=1, le=10000)
    allow_lab_http: bool = False
