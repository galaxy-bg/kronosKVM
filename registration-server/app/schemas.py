import base64
import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .crypto import public_key


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Identity(Strict):
    serial: str = Field(pattern=r"^[0-9a-fA-F]{16}$")
    installation_id: UUID
    public_key: str = Field(min_length=44, max_length=44)

    @field_validator("serial")
    @classmethod
    def normalize(cls, value):
        return value.upper()

    @field_validator("public_key")
    @classmethod
    def validate_key(cls, value):
        public_key(value)
        return value


class Enroll(Identity):
    firmware: str = Field(min_length=1, max_length=120)
    model: str = Field(min_length=1, max_length=120)


class ChallengeInput(Identity):
    purpose: Literal["authenticate", "activate"] = "authenticate"


class Proof(Strict):
    challenge_id: UUID
    signature: str = Field(min_length=88, max_length=88)

    @field_validator("signature")
    @classmethod
    def signature_valid(cls, value):
        if len(base64.b64decode(value, validate=True)) != 64:
            raise ValueError("Invalid signature length")
        return value


class Activate(Proof):
    activation_token: str = Field(min_length=32, max_length=200)


class CustomerInput(Strict):
    name: str = Field(min_length=1, max_length=200)
    contact_name: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=40)

    @field_validator("name", "contact_name", "phone")
    @classmethod
    def strip_text(cls, value):
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Text must not be blank")
        return value

    @field_validator("email")
    @classmethod
    def email_format(cls, value):
        if value is None or value == "":
            return None
        value = value.strip()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("Invalid email address")
        local, domain = value.rsplit("@", 1)
        return local + "@" + domain.lower()


class CustomerUpdate(CustomerInput):
    reason: str = Field(min_length=5, max_length=500)


class DeviceCreate(Strict):
    serial: str = Field(pattern=r"^[0-9a-fA-F]{16}$")
    model: str = Field(min_length=1, max_length=120)
    display_name: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=1000)
    customer_id: UUID | None = None

    @field_validator("serial")
    @classmethod
    def serial_format(cls, value):
        value = value.upper()
        if value in {"0" * 16, "F" * 16}:
            raise ValueError("Invalid hardware serial")
        return value

    @field_validator("model")
    @classmethod
    def model_format(cls, value):
        if not value.strip():
            raise ValueError("Model required")
        return value.strip()


class DeviceUpdate(Strict):
    display_name: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=1000)
    customer_id: UUID | None = None
    reason: str = Field(min_length=5, max_length=500)


class LicenseInput(Strict):
    customer_id: UUID
    kind: Literal["PERPETUAL", "SUBSCRIPTION", "RENTAL", "DEMO"]
    expires_at: datetime | None = None
    max_devices: int = Field(default=1, ge=1, le=100000)

    @field_validator("expires_at")
    @classmethod
    def aware(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError("Timezone required")
        return value


class Approval(Strict):
    installation_id: UUID
    public_key: str
    license_id: UUID
    reason: str = Field(min_length=5, max_length=500)
    token_ttl_seconds: int = Field(default=3600, ge=60, le=86400)

    @field_validator("public_key")
    @classmethod
    def key_valid(cls, value):
        public_key(value)
        return value


class Reason(Strict):
    reason: str = Field(min_length=5, max_length=500)


class Renewal(Reason):
    expires_at: datetime

    @field_validator("expires_at")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError("Timezone required")
        return value
