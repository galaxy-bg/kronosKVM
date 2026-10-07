"""Authenticated browser sessions; target credentials travel in a WS body only."""

import asyncio
import os
import uuid
from typing import Literal

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, ValidationError

from backend.app.logging import audit
from backend.app.services.connections import list_connections
from backend.app.services.guacamole import (
    InstructionReader,
    handshake,
    instruction,
    parse_instruction,
)
from backend.app.services.tasks import finish_task, start_task

router = APIRouter(prefix="/api/v1/remote", tags=["remote connections"])
_active = set()
MAX_SESSIONS = 4


class SessionInput(BaseModel):
    profile_id: str = Field(min_length=1, max_length=64)
    username: str = Field(default="", max_length=64)
    password: str = Field(default="", max_length=4096)
    domain: str = Field(default="", max_length=64)
    width: int = Field(default=1280, ge=640, le=2560)
    height: int = Field(default=720, ge=480, le=1440)
    ignore_certificate: bool = False
    security: Literal["any", "nla", "tls", "rdp"] = "any"


def connection_parameters(profile, value):
    return {
        "hostname": profile.host,
        "port": str(profile.port),
        "username": value.username or profile.username or "",
        "password": value.password,
        "domain": value.domain,
        "security": value.security,
        "ignore-cert": "true" if value.ignore_certificate else "false",
        "resize-method": "display-update",
        "disable-audio": "true",
        "enable-drive": "false",
        "enable-printing": "false",
        "disable-copy": "true",
        "disable-paste": "true",
        "font-name": "monospace",
        "font-size": "14",
        "color-depth": "24",
    }


@router.websocket("/ws")
async def remote_console(websocket: WebSocket):
    await websocket.accept()
    session_id = str(uuid.uuid4())
    writer = None
    jobs = []
    started = False
    result = "disconnected"
    try:
        if len(_active) >= MAX_SESSIONS:
            await websocket.send_text(
                instruction("error", "Four remote sessions are already open.", "513")
            )
            return
        _active.add(session_id)
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=15)
        if len(raw) > 16384:
            raise ValueError("Session request too large")
        value = SessionInput.model_validate_json(raw)
        profile = next((p for p in list_connections() if p.id == value.profile_id), None)
        if profile is None or profile.type not in {"telnet", "rdp", "vnc"}:
            raise ValueError("Unknown remote connection profile")
        parameters = connection_parameters(profile, value)
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(
                os.environ.get("KRONOSKVM_GUACD_HOST", "127.0.0.1"),
                int(os.environ.get("KRONOSKVM_GUACD_PORT", "4822")),
            ),
            timeout=5,
        )
        reader = InstructionReader(reader)
        tunnel_id = await handshake(
            reader, writer, profile.type, parameters, value.width, value.height
        )
        # Release credential references after guacd has accepted the handshake.
        parameters.clear()
        value.password = ""
        raw = ""
        start_task(
            f"session.{profile.type}",
            f"{profile.type.upper()} session · {profile.name}",
            task_id=session_id,
            detail=f"{profile.host}:{profile.port}",
            source="session",
        )
        started = True
        audit(
            "remote.session.started",
            session_id=session_id,
            protocol=profile.type,
            target=profile.host,
            port=profile.port,
        )
        await websocket.send_text(instruction("", tunnel_id))

        async def gateway_to_browser():
            nonlocal result
            while True:
                elements, frame = await reader.read()
                if elements[0] == "error":
                    result = "failed"
                await websocket.send_text(frame)

        async def browser_to_gateway():
            while True:
                data = await websocket.receive_text()
                if len(data) > 65536:
                    raise ValueError("Input frame too large")
                remaining = data
                while remaining:
                    parsed = parse_instruction(remaining)
                    if not parsed:
                        raise ValueError("Incomplete input instruction")
                    elements, consumed = parsed
                    if elements[0] not in {
                        "key",
                        "mouse",
                        "sync",
                        "size",
                        "disconnect",
                        "nop",
                        "ack",
                    }:
                        raise ValueError("Unsupported input instruction")
                    if elements[0] == "size":
                        if len(elements) != 3 or not (
                            640 <= int(elements[1]) <= 2560 and 480 <= int(elements[2]) <= 1440
                        ):
                            raise ValueError("Invalid display size")
                    writer.write(remaining[:consumed].encode())
                    remaining = remaining[consumed:]
                await writer.drain()

        jobs = [
            asyncio.create_task(gateway_to_browser()),
            asyncio.create_task(browser_to_gateway()),
        ]
        done, _ = await asyncio.wait(jobs, return_when=asyncio.FIRST_COMPLETED)
        for job in done:
            job.result()
    except (WebSocketDisconnect, EOFError):
        pass
    except (OSError, ValueError, ValidationError, asyncio.TimeoutError) as error:
        result = "failed"
        audit("remote.session.failed", session_id=session_id, error=type(error).__name__)
        try:
            await websocket.send_text(
                instruction(
                    "error", "Connection failed. Check the gateway, target and credentials.", "519"
                )
            )
        except (WebSocketDisconnect, RuntimeError):
            pass
    finally:
        for job in jobs:
            if not job.done():
                job.cancel()
        if jobs:
            await asyncio.gather(*jobs, return_exceptions=True)
        if writer:
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), timeout=3)
            except (OSError, asyncio.TimeoutError):
                pass
        _active.discard(session_id)
        if started:
            finish_task(session_id, result != "failed", result)
        audit("remote.session.ended", session_id=session_id, result=result)
        try:
            await websocket.close()
        except (WebSocketDisconnect, RuntimeError):
            pass
