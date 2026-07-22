import asyncio
import json

import asyncssh
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(prefix="/api/v1/ssh", tags=["ssh"])


@router.websocket("/ws")
async def ssh_console(websocket: WebSocket) -> None:
    await websocket.accept()
    connection = None
    process = None
    try:
        credentials = json.loads(await websocket.receive_text())
        host = str(credentials.get("host", "")).strip()
        username = str(credentials.get("username", "")).strip()
        password = str(credentials.get("password", ""))
        port = int(credentials.get("port", 22))
        if not host or not username or not 1 <= port <= 65535:
            await websocket.send_text("\r\n[KronosKVM: host, username and port are required]\r\n")
            await websocket.close(code=1008)
            return
        connection = await asyncssh.connect(
            host, port=port, username=username, password=password or None,
            known_hosts=None, login_timeout=15,
        )
        process = await connection.create_process(term_type="xterm-256color", term_size=(120, 34))
        await websocket.send_text("\r\n[KronosKVM: SSH connected]\r\n")

        async def ssh_to_web() -> None:
            while True:
                data = await process.stdout.read(4096)
                if not data:
                    break
                await websocket.send_text(data)

        async def web_to_ssh() -> None:
            while True:
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    raise WebSocketDisconnect(message.get("code", 1000))
                data = message.get("text")
                if data is None and message.get("bytes") is not None:
                    data = message["bytes"].decode("utf-8", errors="replace")
                if data:
                    process.stdin.write(data)

        tasks = [asyncio.create_task(ssh_to_web()), asyncio.create_task(web_to_ssh())]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*done, *pending, return_exceptions=True)
    except (asyncssh.Error, OSError, ValueError, json.JSONDecodeError) as error:
        await websocket.send_text(f"\r\n[KronosKVM: SSH connection failed: {error}]\r\n")
    except WebSocketDisconnect:
        pass
    finally:
        if process is not None:
            process.stdin.close()
        if connection is not None:
            connection.close()
            await connection.wait_closed()
        try:
            await websocket.close()
        except RuntimeError:
            pass
