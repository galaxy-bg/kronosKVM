from __future__ import annotations

import errno
import json
import os
import struct
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.app.logging import audit
from backend.app.services.tasks import finish_task, start_task

router = APIRouter(prefix="/api/v1/hid", tags=["hid"])

KEYBOARD_DEVICE = Path("/dev/hidg0")
MOUSE_DEVICE = Path("/dev/hidg1")
RELATIVE_MOUSE_DEVICE = MOUSE_DEVICE


def _write_report(device: Path, report: bytes) -> None:
    descriptor = os.open(device, os.O_WRONLY | os.O_NONBLOCK)
    try:
        try:
            os.write(descriptor, report)
        except BlockingIOError:
            # The target may not have claimed this HID interface yet (common
            # during BIOS/UEFI transitions). Drop this report without blocking
            # the API event loop; the next browser input will retry.
            pass
        except OSError as error:
            # A disconnected or unclaimed composite HID endpoint must not tear
            # down the WebSocket used by the other keyboard/mouse interfaces.
            if error.errno not in {errno.ENODEV, errno.ESHUTDOWN, errno.EPIPE}:
                raise
    finally:
        os.close(descriptor)


@router.get("/status")
def hid_status() -> dict:
    return {
        "ready": KEYBOARD_DEVICE.exists() and MOUSE_DEVICE.exists(),
        "keyboard": KEYBOARD_DEVICE.exists(),
        "mouse": MOUSE_DEVICE.exists(),
        "relative_mouse": RELATIVE_MOUSE_DEVICE.exists(),
    }


@router.websocket("/ws")
async def hid_websocket(websocket: WebSocket) -> None:
    session_id = str(uuid.uuid4())
    started = time.monotonic()
    keyboard_reports = 0
    mouse_reports = 0
    await websocket.accept()
    start_task(
        "session.hid",
        "KVM keyboard and mouse session",
        task_id=session_id,
        source="session",
    )
    audit(
        "hid.session.started",
        session_id=session_id,
        client=websocket.client.host if websocket.client else None,
    )
    try:
        while True:
            message = json.loads(await websocket.receive_text())
            if message.get("type") == "keyboard":
                keyboard_reports += 1
                modifiers = max(0, min(255, int(message.get("modifiers", 0))))
                keys = [max(0, min(255, int(key))) for key in message.get("keys", [])][:6]
                report = bytes([modifiers, 0, *keys, *([0] * (6 - len(keys)))])
                _write_report(KEYBOARD_DEVICE, report)
            elif message.get("type") == "mouse":
                mouse_reports += 1
                buttons = max(0, min(7, int(message.get("buttons", 0))))
                x = max(-127, min(127, int(message.get("x", 0))))
                y = max(-127, min(127, int(message.get("y", 0))))
                _write_report(MOUSE_DEVICE, struct.pack("<Bbb", buttons, x, y))
    except (
        WebSocketDisconnect,
        FileNotFoundError,
        PermissionError,
        ValueError,
    ):
        pass
    finally:
        finish_task(session_id, True)
        audit(
            "hid.session.ended",
            session_id=session_id,
            duration_ms=round((time.monotonic() - started) * 1000, 1),
            keyboard_reports=keyboard_reports,
            mouse_reports=mouse_reports,
        )
