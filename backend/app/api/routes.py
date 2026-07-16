import socket

from fastapi import APIRouter

from backend.app.hardware import display, ports, rtc, serial, temperature, usb_gadget, video
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
