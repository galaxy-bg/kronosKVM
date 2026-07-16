import os
import platform
import shutil
from pathlib import Path

from fastapi import APIRouter

from backend.app.models import Capability, HardwareStatus

router = APIRouter(prefix="/api/v1")


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.1.0"}


@router.get("/capabilities", response_model=list[Capability])
def capabilities() -> list[Capability]:
    return [
        Capability(name="video", status=HardwareStatus.WAITING_FOR_HARDWARE),
        Capability(name="hid", status=HardwareStatus.DISABLED),
        Capability(name="virtual_media", status=HardwareStatus.DISABLED),
        Capability(name="serial", status=HardwareStatus.DISABLED),
        Capability(name="rtc", status=HardwareStatus.NOT_DETECTED),
        Capability(name="display", status=HardwareStatus.NOT_DETECTED),
    ]


@router.get("/system/info")
def system_info() -> dict[str, object]:
    model_path = Path("/proc/device-tree/model")
    try:
        model = model_path.read_text(encoding="utf-8").rstrip("\x00\n")
    except OSError:
        model = "unknown"
    return {
        "hostname": platform.node(),
        "model": model,
        "architecture": platform.machine(),
        "kernel": platform.release(),
        "load_average": list(os.getloadavg()),
    }


@router.get("/system/network")
def network_info() -> dict[str, object]:
    return {"status": "discovery_pending", "interfaces": []}


@router.get("/system/storage")
def storage_info() -> dict[str, object]:
    usage = shutil.disk_usage("/")
    return {"root_total_bytes": usage.total, "root_free_bytes": usage.free}


@router.get("/system/services")
def services_info() -> dict[str, object]:
    return {"status": "not_installed", "services": []}


def _hardware(status: HardwareStatus, detail: str) -> dict[str, str]:
    return {"status": status.value, "detail": detail}


@router.get("/hardware/usb")
def usb_info() -> dict[str, str]:
    return _hardware(HardwareStatus.NOT_DETECTED, "UDC discovery pending")


@router.get("/hardware/video")
def video_info() -> dict[str, str]:
    return _hardware(HardwareStatus.WAITING_FOR_HARDWARE, "HDMI-to-CSI module absent")


@router.get("/hardware/serial")
def serial_info() -> dict[str, str]:
    return _hardware(HardwareStatus.DISABLED, "Serial transport is disabled")


@router.get("/hardware/rtc")
def rtc_info() -> dict[str, str]:
    return _hardware(HardwareStatus.NOT_DETECTED, "RTC discovery pending")


@router.get("/hardware/temperature")
def temperature_info() -> dict[str, object]:
    path = Path("/sys/class/thermal/thermal_zone0/temp")
    try:
        value = int(path.read_text(encoding="utf-8").strip()) / 1000
    except (OSError, ValueError):
        value = None
    return {"status": "ready" if value is not None else "not_detected", "celsius": value}
