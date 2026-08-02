import os
import socket
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from backend.app.hardware import display, ports, rtc, serial, temperature, usb_gadget, video
from backend.app.logging import audit
from backend.app.models import (
    Capability,
    HealthResponse,
    NetworkInfo,
    PhysicalPortInventory,
    ServicesInfo,
    StorageInfo,
    SystemInfo,
    TemperatureInfo,
)
from backend.app.services.system import (
    get_network_info,
    get_services_info,
    get_storage_info,
    get_system_info,
)

router = APIRouter(prefix="/api/v1")
POWER_ACTION_PATH = Path(
    os.environ.get("KRONOSKVM_POWER_ACTION_PATH", "/state/power-action")
)


class PowerActionRequest(BaseModel):
    action: Literal["reboot", "poweroff"]
    confirmed: bool = False


def get_capabilities() -> list[Capability]:
    return [
        video.capability(),
        usb_gadget.capability(),
        Capability(
            name="virtual_media",
            status=usb_gadget.capability().status,
            detail="Requires a verified USB device controller",
        ),
        serial.capability(),
        rtc.capability(),
        display.capability(),
        temperature.capability(),
    ]


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", version="0.1.0", hostname=socket.gethostname())


@router.get("/capabilities", response_model=list[Capability])
def capabilities() -> list[Capability]:
    return get_capabilities()


@router.get("/system/info", response_model=SystemInfo)
def system_info() -> SystemInfo:
    return get_system_info()


@router.get("/system/network", response_model=NetworkInfo)
def network_info() -> NetworkInfo:
    return get_network_info()


@router.get("/system/storage", response_model=StorageInfo)
def storage_info() -> StorageInfo:
    return get_storage_info()


@router.get("/system/services", response_model=ServicesInfo)
def services_info() -> ServicesInfo:
    return get_services_info()


@router.post("/system/power", status_code=status.HTTP_202_ACCEPTED)
def system_power(request: PowerActionRequest) -> dict:
    if not request.confirmed:
        raise HTTPException(status_code=400, detail="Explicit confirmation is required")
    try:
        POWER_ACTION_PATH.parent.mkdir(parents=True, exist_ok=True)
        pending = POWER_ACTION_PATH.with_suffix(".pending")
        pending.write_text(f"{request.action}\n", encoding="ascii")
        pending.replace(POWER_ACTION_PATH)
    except OSError as error:
        raise HTTPException(status_code=503, detail="Power control is unavailable") from error
    audit("system.power.requested", action=request.action)
    return {"accepted": True, "action": request.action}


@router.get("/hardware/usb", response_model=Capability)
def usb_info() -> Capability:
    return usb_gadget.capability()


@router.get("/hardware/video", response_model=Capability)
def video_info() -> Capability:
    return video.capability()


@router.get("/hardware/serial", response_model=Capability)
def serial_info() -> Capability:
    return serial.capability()


@router.get("/hardware/rtc", response_model=Capability)
def rtc_info() -> Capability:
    return rtc.capability()


@router.get("/hardware/temperature", response_model=TemperatureInfo)
def temperature_info() -> TemperatureInfo:
    value = temperature.read_temperature()
    return TemperatureInfo(
        status="ready" if value is not None else "not_detected",
        celsius=value,
    )


@router.get("/hardware/ports", response_model=PhysicalPortInventory)
def port_info() -> PhysicalPortInventory:
    return ports.physical_ports()
