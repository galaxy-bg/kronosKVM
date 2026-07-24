from __future__ import annotations

import json
import struct
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(prefix="/api/v1/hid", tags=["hid"])

KEYBOARD_DEVICE = Path("/dev/hidg0")
MOUSE_DEVICE = Path("/dev/hidg1")
RELATIVE_MOUSE_DEVICE = Path("/dev/hidg2")


def _write_report(device: Path, report: bytes) -> None:
    with device.open("wb", buffering=0) as output:
        output.write(report)


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
    await websocket.accept()
    try:
        while True:
            message = json.loads(await websocket.receive_text())
            if message.get("type") == "keyboard":
                modifiers = max(0, min(255, int(message.get("modifiers", 0))))
                keys = [max(0, min(255, int(key))) for key in message.get("keys", [])][:6]
                report = bytes([modifiers, 0, *keys, *([0] * (6 - len(keys)))])
                _write_report(KEYBOARD_DEVICE, report)
            elif message.get("type") == "mouse":
                buttons = max(0, min(7, int(message.get("buttons", 0))))
                wheel = max(-127, min(127, int(message.get("wheel", 0))))
                if message.get("mode") == "relative":
                    x = max(-127, min(127, int(message.get("x", 0))))
                    y = max(-127, min(127, int(message.get("y", 0))))
                    _write_report(
                        RELATIVE_MOUSE_DEVICE,
                        struct.pack("<Bbbb", buttons, x, y, wheel),
                    )
                else:
                    x = max(0, min(32767, int(message.get("x", 0))))
                    y = max(0, min(32767, int(message.get("y", 0))))
                    _write_report(
                        MOUSE_DEVICE,
                        struct.pack("<BHHb", buttons, x, y, wheel),
                    )
    except (WebSocketDisconnect, FileNotFoundError, PermissionError, ValueError):
        return
