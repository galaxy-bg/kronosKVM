import ipaddress
import os
import re
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from backend.app.services.system import get_network_info

router = APIRouter(prefix="/api/v1/network/settings", tags=["network"])
STATE_PATH = Path(os.environ.get("KRONOSKVM_STATE_PATH", "/state"))
REQUEST_PATH = STATE_PATH / "network-action"
NET_ROOT = Path("/sys/class/net")
INTERFACE_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,15}$")


class NetworkSettingsInput(BaseModel):
    interface: str = Field(min_length=1, max_length=15)
    mode: Literal["dhcp", "static"]
    address: Optional[str] = None
    gateway: Optional[str] = None
    dns: list[str] = Field(default_factory=list, max_length=3)
    confirmed: bool = False


def _eligible_interfaces() -> list[str]:
    try:
        paths = sorted(NET_ROOT.iterdir())
    except OSError:
        return []
    return [
        path.name
        for path in paths
        if path.name not in {"lo", "wlan0"}
        and INTERFACE_PATTERN.fullmatch(path.name)
        and not (path / "wireless").exists()
        and (path / "device").exists()
    ]


def _saved_values(interface: str) -> dict[str, str]:
    path = STATE_PATH / f"network-config-{interface}"
    values: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="ascii").splitlines():
            key, separator, value = line.partition("=")
            if separator and key in {"mode", "address", "gateway", "dns", "status", "message"}:
                values[key] = value
    except OSError:
        pass
    return values


@router.get("")
def list_network_settings() -> dict:
    live = {item.name: item for item in get_network_info().interfaces}
    entries = []
    for name in _eligible_interfaces():
        saved = _saved_values(name)
        item = live.get(name)
        entries.append(
            {
                "interface": name,
                "state": item.state if item else "unknown",
                "mac_address": item.mac_address if item else None,
                "current_addresses": item.addresses if item else [],
                "mode": saved.get("mode", "dhcp"),
                "address": saved.get("address") or None,
                "gateway": saved.get("gateway") or None,
                "dns": [value for value in saved.get("dns", "").split(",") if value],
                "apply_status": saved.get("status", "ready"),
                "message": saved.get("message") or None,
            }
        )
    return {"interfaces": entries, "protected_interfaces": ["wlan0"]}


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def apply_network_settings(value: NetworkSettingsInput) -> dict:
    if not value.confirmed:
        raise HTTPException(status_code=400, detail="Explicit confirmation is required")
    if value.interface not in _eligible_interfaces():
        raise HTTPException(status_code=400, detail="Interface is unavailable or protected")
    address = ""
    gateway = ""
    dns: list[str] = []
    if value.mode == "static":
        if not value.address:
            raise HTTPException(
                status_code=400,
                detail="Static IPv4 address and prefix are required",
            )
        try:
            configured = ipaddress.IPv4Interface(value.address)
            address = str(configured)
            if value.gateway:
                parsed_gateway = ipaddress.IPv4Address(value.gateway)
                if parsed_gateway not in configured.network:
                    raise ValueError("Gateway is outside the configured subnet")
                gateway = str(parsed_gateway)
            dns = [str(ipaddress.IPv4Address(item)) for item in value.dns]
        except ValueError as error:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid static IPv4 configuration: {error}",
            ) from error
    try:
        STATE_PATH.mkdir(parents=True, exist_ok=True)
        pending = STATE_PATH / ".network-action.tmp"
        pending.write_text(
            "\n".join(
                [
                    f"interface={value.interface}",
                    f"mode={value.mode}",
                    f"address={address}",
                    f"gateway={gateway}",
                    f"dns={','.join(dns)}",
                    "",
                ]
            ),
            encoding="ascii",
        )
        pending.replace(REQUEST_PATH)
    except OSError as error:
        raise HTTPException(status_code=503, detail="Network host helper is unavailable") from error
    return {"accepted": True, "interface": value.interface, "mode": value.mode}
