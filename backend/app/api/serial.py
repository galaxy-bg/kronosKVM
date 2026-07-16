from fastapi import APIRouter, HTTPException, status

from backend.app.hardware.serial import discover_devices
from backend.app.models import (
    SerialInventory,
    SerialLock,
    SerialLockRequest,
    SerialUnlockRequest,
)
from backend.app.services.serial import load_profiles, serial_locks

router = APIRouter(prefix="/api/v1/serial", tags=["serial"])


@router.get("/devices", response_model=SerialInventory)
def devices() -> SerialInventory:
    return SerialInventory(
        devices=discover_devices(),
        profiles=load_profiles(),
        tcp_exposure_enabled=False,
    )


@router.post("/locks", response_model=SerialLock, status_code=status.HTTP_201_CREATED)
def acquire_lock(request: SerialLockRequest) -> SerialLock:
    known_devices = {device.device for device in discover_devices()}
    if request.device not in known_devices:
        raise HTTPException(status_code=404, detail="Serial device not detected")
    lock = serial_locks.acquire(request.device, request.owner)
    if lock is None:
        raise HTTPException(status_code=409, detail="Serial device is already locked")
    return lock


@router.delete("/locks/{device_name}", status_code=status.HTTP_204_NO_CONTENT)
def release_lock(device_name: str, request: SerialUnlockRequest) -> None:
    device = f"/dev/{device_name}"
    if not serial_locks.release(device, request.token):
        raise HTTPException(status_code=403, detail="Invalid serial lock token")
