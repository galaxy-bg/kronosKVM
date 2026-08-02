import asyncio
import time
import uuid
from pathlib import Path
from typing import Optional

import serial
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, status

from backend.app.hardware.serial import discover_devices
from backend.app.logging import audit
from backend.app.models import (
    SerialInventory,
    SerialLock,
    SerialLockRequest,
    SerialUnlockRequest,
)
from backend.app.services.serial import load_profiles, serial_locks
from backend.app.services.tasks import finish_task, start_task

router = APIRouter(prefix="/api/v1/serial", tags=["serial"])

PARITY = {
    "none": serial.PARITY_NONE,
    "even": serial.PARITY_EVEN,
    "odd": serial.PARITY_ODD,
}
AUTO_BAUD_RATES = (115200, 9600, 38400, 19200, 57600)
active_sessions: dict[str, tuple[WebSocket, str]] = {}


def _probe_baud_rate(
    device: str,
    data_bits: int,
    parity: str,
    stop_bits: float,
    flow_control: str,
) -> Optional[tuple[int, bytes]]:
    best: Optional[tuple[float, int, bytes]] = None
    for baud_rate in AUTO_BAUD_RATES:
        try:
            with serial.Serial(
                port=device,
                baudrate=baud_rate,
                bytesize=data_bits,
                parity=PARITY[parity],
                stopbits=stop_bits,
                xonxoff=flow_control == "software",
                rtscts=flow_control == "hardware",
                timeout=0.7,
                write_timeout=1,
            ) as candidate:
                candidate.reset_input_buffer()
                candidate.write(b"\r")
                payload = candidate.read(256)
        except (OSError, serial.SerialException):
            continue
        if not payload:
            continue
        printable = sum(byte in (9, 10, 13) or 32 <= byte <= 126 for byte in payload)
        ratio = printable / len(payload)
        score = ratio + min(len(payload), 64) / 256
        if ratio >= 0.75 and (best is None or score > best[0]):
            best = (score, baud_rate, payload)
    return (best[1], best[2]) if best else None


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


@router.delete("/sessions/{device_name}", status_code=status.HTTP_204_NO_CONTENT)
async def reset_session(device_name: str) -> None:
    if Path(device_name).name != device_name or not device_name.startswith(("ttyUSB", "ttyACM")):
        raise HTTPException(status_code=400, detail="Invalid serial device")
    device = f"/dev/{device_name}"
    active = active_sessions.pop(device, None)
    if active is not None:
        websocket, token = active
        serial_locks.release(device, token)
        try:
            await websocket.close(code=4410, reason="operator reset")
        except RuntimeError:
            pass
    else:
        serial_locks.force_release(device)


@router.websocket("/ws/{device_name}")
async def serial_console(
    websocket: WebSocket,
    device_name: str,
    baud_rate: str = "9600",
    data_bits: int = 8,
    parity: str = "none",
    stop_bits: float = 1,
    flow_control: str = "none",
) -> None:
    session_id = str(uuid.uuid4())
    started = time.monotonic()
    received_bytes = 0
    sent_bytes = 0
    result = "disconnected"
    device = f"/dev/{device_name}"
    known_devices = {item.device for item in discover_devices()}
    valid_name = Path(device_name).name == device_name and device_name.startswith(
        ("ttyUSB", "ttyACM")
    )
    try:
        numeric_baud_rate = int(baud_rate) if baud_rate != "auto" else None
    except ValueError:
        numeric_baud_rate = -1
    valid_settings = (
        (baud_rate == "auto" or 50 <= numeric_baud_rate <= 4_000_000)
        and data_bits in {5, 6, 7, 8}
        and parity in PARITY
        and stop_bits in {1, 1.5, 2}
        and flow_control in {"none", "software", "hardware"}
    )
    if not valid_name or device not in known_devices or not valid_settings:
        audit("serial.session.rejected", session_id=session_id, device=device)
        await websocket.close(code=4404)
        return

    lock = serial_locks.acquire(device, "web-console")
    if lock is None:
        audit("serial.session.busy", session_id=session_id, device=device)
        await websocket.accept()
        await websocket.send_text(
            "\r\n[KronosKVM: serial port is already open in another terminal]\r\n"
        )
        await websocket.close(code=4409)
        return

    connection = None
    await websocket.accept()
    active_sessions[device] = (websocket, lock.token)
    start_task(
        "session.serial",
        f"Serial console session · {Path(device).name}",
        task_id=session_id,
        detail=device,
        source="session",
    )
    audit(
        "serial.session.started",
        session_id=session_id,
        client=websocket.client.host if websocket.client else None,
        device=device,
        baud_rate=baud_rate,
        data_bits=data_bits,
        parity=parity,
        stop_bits=stop_bits,
        flow_control=flow_control,
    )
    try:
        initial_payload = b""
        if baud_rate == "auto":
            probe = await asyncio.to_thread(
                _probe_baud_rate,
                device,
                data_bits,
                parity,
                stop_bits,
                flow_control,
            )
            if probe is None:
                result = "baud_detection_failed"
                await websocket.send_text("\r\n[KronosKVM: baud rate could not be detected]\r\n")
                await websocket.close(code=4408)
                return
            numeric_baud_rate, initial_payload = probe
            await websocket.send_text(
                f"\r\n[KronosKVM: auto-detected {numeric_baud_rate} baud]\r\n"
            )
        connection = serial.Serial(
            port=device,
            baudrate=numeric_baud_rate,
            bytesize=data_bits,
            parity=PARITY[parity],
            stopbits=stop_bits,
            xonxoff=flow_control == "software",
            rtscts=flow_control == "hardware",
            timeout=0.1,
            write_timeout=1,
        )
        result = "connected"
        if initial_payload:
            await websocket.send_bytes(initial_payload)

        async def serial_to_web() -> None:
            nonlocal received_bytes
            while True:
                payload = await asyncio.to_thread(connection.read, 1024)
                if payload:
                    received_bytes += len(payload)
                    await websocket.send_bytes(payload)

        async def web_to_serial() -> None:
            nonlocal sent_bytes
            while True:
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    raise WebSocketDisconnect(message.get("code", 1000))
                payload = message.get("bytes")
                if payload is None and message.get("text") is not None:
                    payload = message["text"].encode()
                if payload:
                    sent_bytes += len(payload)
                    await asyncio.to_thread(connection.write, payload)

        tasks = [
            asyncio.create_task(serial_to_web()),
            asyncio.create_task(web_to_serial()),
        ]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
        for task in pending:
            task.cancel()
        for task in done:
            task.result()
    except (OSError, serial.SerialException, WebSocketDisconnect):
        pass
    finally:
        session_successful = result not in {"baud_detection_failed"}
        finish_task(
            session_id,
            session_successful,
            None if session_successful else result,
        )
        current = active_sessions.get(device)
        if current is not None and current[0] is websocket:
            active_sessions.pop(device, None)
        if connection is not None and connection.is_open:
            connection.close()
        serial_locks.release(device, lock.token)
        audit(
            "serial.session.ended",
            session_id=session_id,
            device=device,
            result=result,
            duration_ms=round((time.monotonic() - started) * 1000, 1),
            bytes_from_device=received_bytes,
            bytes_to_device=sent_bytes,
        )
