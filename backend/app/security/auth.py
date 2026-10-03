"""Single-admin authentication; only credential changes write to persistent storage."""

import asyncio
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from collections import deque
from pathlib import Path
from typing import Optional

from fastapi import HTTPException
from starlette.datastructures import Headers
from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse
from starlette.websockets import WebSocketDisconnect

COOKIE = "__Host-infrabox-session"
SESSION_SECONDS = 8 * 3600
IDLE_SECONDS = 30 * 60
PUBLIC = {"/api/v1/health", "/api/v1/auth/login", "/api/v1/auth/session"}


def password_hash(password: str, salt: str) -> str:
    return hashlib.scrypt(
        password.encode(),
        salt=bytes.fromhex(salt),
        n=32768,
        r=8,
        p=3,
        maxmem=64 * 1024 * 1024,
    ).hex()


class AuthStore:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()
        self.credentials = None
        self.sessions = {}
        self.attempts = {}
        self.global_attempts = deque()

    def _load(self):
        if self.credentials is not None:
            return self.credentials
        try:
            value = json.loads(self.path.read_text())
            if (
                value.get("username") != "admin"
                or not isinstance(value.get("must_change_password"), bool)
                or len(bytes.fromhex(value["salt"])) != 16
                or len(bytes.fromhex(value["hash"])) != 64
            ):
                raise ValueError("Invalid credentials")
        except FileNotFoundError:
            salt = secrets.token_hex(16)
            value = {
                "username": "admin",
                "salt": salt,
                "hash": password_hash("ChangeMe", salt),
                "must_change_password": False,
            }
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
            raise HTTPException(503, "Authentication storage is unavailable") from error
        self.credentials = value
        return value

    def _save(self, value):
        temporary = self.path.with_name(self.path.name + ".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w") as stream:
                json.dump(value, stream)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self.path)
            directory = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except OSError as error:
            raise HTTPException(503, "Authentication storage is unavailable") from error
        self.credentials = value

    def _new_session(self):
        now = time.monotonic()
        self.sessions = {
            k: v
            for k, v in self.sessions.items()
            if now < v["expires"] and now - v["last_seen"] < IDLE_SECONDS
        }
        if len(self.sessions) >= 32:
            del self.sessions[min(self.sessions, key=lambda k: self.sessions[k]["last_seen"])]
        token = secrets.token_urlsafe(32)
        self.sessions[token] = {"expires": now + SESSION_SECONDS, "last_seen": now}
        return token

    def login(self, username, password, client):
        with self.lock:
            now = time.monotonic()
            self.attempts = {k: v for k, v in self.attempts.items() if v and now - v[-1] < 60}
            attempts = self.attempts.setdefault(client, deque())
            for queue in (attempts, self.global_attempts):
                while queue and now - queue[0] >= 60:
                    queue.popleft()
            if len(attempts) >= 5 or len(self.global_attempts) >= 30:
                raise HTTPException(
                    429,
                    "Too many login attempts. Try again in a minute.",
                    headers={"Retry-After": "60"},
                )
            attempts.append(now)
            self.global_attempts.append(now)
            value = self._load()
            matches = hmac.compare_digest(password_hash(password, value["salt"]), value["hash"])
            if username != "admin" or not matches:
                raise HTTPException(401, "Invalid username or password")
            if not self.path.exists():
                self._save(value)
            return self._new_session(), False

    def session(self, token, touch=True) -> Optional[dict]:
        with self.lock:
            value = self.sessions.get(token)
            now = time.monotonic()
            if not value or now >= value["expires"] or now - value["last_seen"] >= IDLE_SECONDS:
                self.sessions.pop(token, None)
                return None
            if touch:
                value["last_seen"] = now
            return {
                "username": "admin",
                "must_change_password": False,
            }

    def logout(self, token):
        with self.lock:
            self.sessions.pop(token, None)

    def change_password(self, token, current, new):
        with self.lock:
            if not self.session(token):
                raise HTTPException(401, "Sign in required")
            value = self._load()
            if not hmac.compare_digest(password_hash(current, value["salt"]), value["hash"]):
                raise HTTPException(400, "Current password is incorrect")
            if len(new) < 12 or new == "ChangeMe" or new == current:
                raise HTTPException(400, "Choose a different password with at least 12 characters")
            salt = secrets.token_hex(16)
            self._save(
                {
                    "username": "admin",
                    "salt": salt,
                    "hash": password_hash(new, salt),
                    "must_change_password": False,
                }
            )
            self.sessions.clear()
            return self._new_session()


class AuthMiddleware:
    def __init__(self, app, store):
        self.app = app
        self.store = store

    async def __call__(self, scope, receive, send):
        if scope["type"] not in {"http", "websocket"}:
            return await self.app(scope, receive, send)
        path = scope["path"]
        headers = Headers(scope=scope)
        websocket = scope["type"] == "websocket"
        mutation = scope.get("method") not in {"GET", "HEAD", "OPTIONS"}
        token = HTTPConnection(scope).cookies.get(COOKIE)
        session = self.store.session(token)
        error = None
        code = 401
        if path != "/api/v1/health" and scope["scheme"] not in {"https", "wss"}:
            error, code = "HTTPS is required", 403
        origin = headers.get("origin")
        expected = "https://" + headers.get("host", "")
        if websocket or mutation:
            if (
                (origin and origin != expected)
                or (websocket and not origin)
                or (not websocket and headers.get("x-infrabox-request") != "1")
            ):
                error, code = "Same-origin request required", 403
        if path not in PUBLIC and not session:
            error, code = "Sign in required", 401
        if error:
            if websocket:
                await send({"type": "websocket.close", "code": 4401 if code == 401 else 4403})
            else:
                await JSONResponse(
                    {"detail": error}, status_code=code, headers={"Cache-Control": "no-store"}
                )(scope, receive, send)
            return
        if not websocket:

            async def no_cache(message):
                if message["type"] == "http.response.start":
                    message.setdefault("headers", []).append((b"cache-control", b"no-store"))
                await send(message)

            return await self.app(scope, receive, no_cache)

        # Revoke active consoles after logout/password change, including idle sockets.
        closed = False

        async def revoke():
            nonlocal closed
            if not closed:
                closed = True
                await send({"type": "websocket.close", "code": 4401})

        async def guarded_receive():
            while True:
                if not self.store.session(token, touch=False):
                    await revoke()
                    return {"type": "websocket.disconnect", "code": 4401}
                try:
                    message = await asyncio.wait_for(receive(), timeout=5)
                except asyncio.TimeoutError:
                    continue
                if message["type"] == "websocket.receive":
                    if not self.store.session(token):
                        await revoke()
                        return {"type": "websocket.disconnect", "code": 4401}
                return message

        async def guarded_send(message):
            nonlocal closed
            if closed:
                if message["type"] == "websocket.close":
                    return
                raise WebSocketDisconnect(4401)
            if message["type"] in {"websocket.accept", "websocket.send"}:
                if not self.store.session(token, touch=False):
                    await revoke()
                    raise WebSocketDisconnect(4401)
            if message["type"] == "websocket.close":
                closed = True
            await send(message)

        await self.app(scope, guarded_receive, guarded_send)
