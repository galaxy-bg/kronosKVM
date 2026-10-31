import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now():
    return datetime.now(UTC)


def uid():
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(200))
    contact_name: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(254))
    phone: Mapped[str | None] = mapped_column(String(40))
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING','ACTIVATION_REQUIRED','ACTIVE','SUSPENDED',"
            "'REVOKED','EXPIRED','HARDWARE_MISMATCH')"
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    serial: Mapped[str] = mapped_column(String(16), unique=True)
    model: Mapped[str] = mapped_column(String(120))
    firmware: Mapped[str] = mapped_column(String(120))
    display_name: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default="PENDING")
    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id"))
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Installation(Base):
    __tablename__ = "installations"
    __table_args__ = (
        Index(
            "one_current_installation",
            "device_id",
            unique=True,
            postgresql_where=text("current = true"),
            sqlite_where=text("current = 1"),
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)
    current: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DeviceKey(Base):
    __tablename__ = "device_keys"
    __table_args__ = (
        Index(
            "one_current_key",
            "installation_id",
            unique=True,
            postgresql_where=text("current = true"),
            sqlite_where=text("current = 1"),
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    installation_id: Mapped[str] = mapped_column(ForeignKey("installations.id"), index=True)
    public_key: Mapped[str] = mapped_column(String(44), unique=True)
    current: Mapped[bool] = mapped_column(Boolean, default=False)


class License(Base):
    __tablename__ = "licenses"
    __table_args__ = (
        CheckConstraint("kind IN ('PERPETUAL','SUBSCRIPTION','RENTAL','DEMO')"),
        CheckConstraint("status IN ('ACTIVE','SUSPENDED','REVOKED')"),
        CheckConstraint("max_devices >= 1"),
        CheckConstraint("kind = 'PERPETUAL' OR expires_at IS NOT NULL"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"))
    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    max_devices: Mapped[int] = mapped_column(Integer, default=1)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LicenseBinding(Base):
    __tablename__ = "license_bindings"
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), primary_key=True)
    license_id: Mapped[str] = mapped_column(ForeignKey("licenses.id"), index=True)


class ActivationToken(Base):
    __tablename__ = "activation_tokens"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"))
    installation_id: Mapped[str] = mapped_column(ForeignKey("installations.id"))
    key_id: Mapped[str] = mapped_column(ForeignKey("device_keys.id"))
    license_id: Mapped[str] = mapped_column(ForeignKey("licenses.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Challenge(Base):
    __tablename__ = "challenges"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"))
    installation_id: Mapped[str] = mapped_column(ForeignKey("installations.id"))
    key_id: Mapped[str] = mapped_column(ForeignKey("device_keys.id"))
    serial: Mapped[str] = mapped_column(String(16))
    purpose: Mapped[str] = mapped_column(String(16))
    message: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DeviceSession(Base):
    __tablename__ = "device_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"))
    installation_id: Mapped[str] = mapped_column(ForeignKey("installations.id"))
    key_id: Mapped[str] = mapped_column(ForeignKey("device_keys.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RegistrationEvent(Base):
    __tablename__ = "registration_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    device_id: Mapped[str | None] = mapped_column(ForeignKey("devices.id"))
    kind: Mapped[str] = mapped_column(String(64))
    detail: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    actor: Mapped[str] = mapped_column(String(120))
    action: Mapped[str] = mapped_column(String(64))
    target: Mapped[str] = mapped_column(String(120))
    detail: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Administrator(Base):
    __tablename__ = "administrators"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    role: Mapped[str] = mapped_column(String(16), default="admin")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
