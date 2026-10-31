"""Same-origin dashboard gateway; upstream credentials stay in expiring server sessions."""

import secrets
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from .vpn import Reader

COOKIE = "kdx_dashboard_session"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="KDX_DASHBOARD_", env_file=".env", extra="ignore")
    registration_url: str = "http://172.12.2.77:3000"
    allowed_origins: str = "http://172.12.2.82:8081,http://172.12.2.78:6000"
    allow_lab_http: bool = False
    secure_cookies: bool = False
    vpn_monitor_enabled: bool = False
    vpn_ssh_key: str = "/etc/kdx-dashboard/vpn-reader.key"
    vpn_known_hosts: str = "/etc/kdx-dashboard/vpn-known-hosts"
    session_seconds: int = Field(default=28800, ge=60, le=28800)
    static_directory: str = str(Path(__file__).resolve().parents[1] / "frontend/dist")


class Login(BaseModel):
    token: SecretStr = Field(min_length=32, max_length=200)


def create_app(settings=None, upstream=None):
    cfg = settings or Settings()
    sessions = {}
    attempts = defaultdict(deque)
    vpn_reader = Reader(cfg)
    origins = {v.strip().rstrip("/") for v in cfg.allowed_origins.split(",")}

    @asynccontextmanager
    async def lifespan(app):
        if upstream is None:
            async with httpx.AsyncClient(
                base_url=cfg.registration_url, timeout=15, follow_redirects=False, trust_env=False
            ) as client:
                app.state.upstream = client
                yield
        else:
            app.state.upstream = upstream
            yield
        sessions.clear()

    app = FastAPI(
        title="InfraBox Dashboard",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def guard(request, call_next):
        if request.url.path.startswith("/api/"):
            if request.method in {"POST", "PUT", "DELETE", "PATCH"}:
                if request.headers.get("origin", "").rstrip("/") not in origins:
                    return JSONResponse(
                        {"detail": "İstek kaynağına izin verilmiyor."}, status_code=403
                    )
                chunks = []
                size = 0
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > 16384:
                        return JSONResponse({"detail": "İstek çok büyük."}, status_code=413)
                    chunks.append(chunk)
                request._body = b"".join(chunks)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        return response

    async def remote(method, path, token, payload=None):
        if not cfg.allow_lab_http and not cfg.registration_url.startswith("https://"):
            raise HTTPException(503, "Registration bağlantısı HTTPS gerektiriyor.")
        try:
            response = await app.state.upstream.request(
                method, path, headers={"Authorization": "Bearer " + token}, json=payload
            )
        except httpx.RequestError:
            raise HTTPException(
                503, "Registration Server’a ulaşılamıyor. Tekrar deneyin."
            ) from None
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail")
                if not isinstance(detail, str):
                    detail = "İstek doğrulanamadı."
            except ValueError:
                detail = "Registration isteği tamamlanamadı."
            raise HTTPException(response.status_code if response.status_code < 500 else 502, detail)
        if response.is_redirect:
            raise HTTPException(502, "Beklenmeyen Registration yönlendirmesi.")
        return response.json()

    def session(request, mutation=False):
        sid = request.cookies.get(COOKIE, "")
        value = sessions.get(sid)
        if not value or value["until"] <= time.time():
            sessions.pop(sid, None)
            raise HTTPException(401, "Oturum sona erdi. Tekrar giriş yapın.")
        if mutation:
            if value["actor"]["role"] != "admin":
                raise HTTPException(403, "Bu işlem yönetici yetkisi gerektiriyor.")
            if not secrets.compare_digest(request.headers.get("x-csrf-token", ""), value["csrf"]):
                raise HTTPException(403, "İstek doğrulanamadı. Sayfayı yenileyin.")
        return value

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "kdx-dashboard"}

    @app.post("/api/login")
    async def login(value: Login, request: Request):
        ip = request.client.host if request.client else "unknown"
        tick = time.time()
        if len(attempts) > 5000:
            for key in list(attempts):
                if not attempts[key] or attempts[key][-1] < tick - 900:
                    del attempts[key]
            if len(attempts) > 5000 and ip not in attempts:
                raise HTTPException(429, "Çok fazla giriş denemesi. Daha sonra deneyin.")
        bucket = attempts[ip]
        while bucket and bucket[0] < tick - 900:
            bucket.popleft()
        if len(bucket) >= 10:
            raise HTTPException(429, "Çok fazla giriş denemesi. 15 dakika bekleyin.")
        bucket.append(tick)
        token = value.token.get_secret_value()
        actor = await remote("GET", "/api/v1/admin/session", token)
        sessions.pop(request.cookies.get(COOKIE, ""), None)
        for sid in list(sessions):
            if sessions[sid]["until"] <= tick:
                del sessions[sid]
        if len(sessions) >= 1000:
            raise HTTPException(503, "Oturum kapasitesi dolu.")
        sid = secrets.token_urlsafe(48)
        csrf = secrets.token_urlsafe(32)
        expiry = datetime.fromisoformat(actor["expires_at"].replace("Z", "+00:00")).timestamp()
        sessions[sid] = {
            "token": token,
            "csrf": csrf,
            "actor": actor,
            "until": min(tick + cfg.session_seconds, expiry),
        }
        bucket.clear()
        response = JSONResponse({"actor": actor, "csrf": csrf})
        response.set_cookie(
            COOKIE,
            sid,
            httponly=True,
            secure=cfg.secure_cookies or request.headers.get("origin", "").startswith("https://"),
            samesite="strict",
            max_age=int(sessions[sid]["until"] - tick),
            path="/",
        )
        return response

    @app.get("/api/session")
    async def whoami(request: Request):
        value = session(request)
        actor = await remote("GET", "/api/v1/admin/session", value["token"])
        value["actor"] = actor
        return {"actor": actor, "csrf": value["csrf"]}

    @app.post("/api/logout")
    async def logout(request: Request):
        value = session(request)
        if not secrets.compare_digest(request.headers.get("x-csrf-token", ""), value["csrf"]):
            raise HTTPException(403, "İstek doğrulanamadı.")
        sessions.pop(request.cookies.get(COOKIE, ""), None)
        response = JSONResponse({"ok": True})
        response.delete_cookie(COOKIE, path="/")
        return response

    @app.get("/api/overview")
    async def overview(request: Request, include_archived: bool = False):
        value = session(request)
        # Each source is the Registration API; the dashboard has no database credentials.
        names = ("devices", "customers", "licenses", "events")
        results = [
            await remote("GET", "/api/v1/admin/" + name + "?limit=200" + ("&include_archived=true" if include_archived and name in {"devices", "customers"} else ""), value["token"])
            for name in names
        ]
        return {
            **dict(zip(names, results)),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "truncated": any(len(items) >= 200 for items in results[:3]),
        }

    @app.get("/api/vpn")
    async def vpn_status(request: Request):
        value = session(request)
        devices = await remote("GET", "/api/v1/admin/devices?limit=200", value["token"])
        try:
            return await vpn_reader.read(devices)
        except (OSError, ValueError, TypeError, KeyError, TimeoutError):
            return JSONResponse(
                {"configured": True, "error": "VPN_STATUS_UNAVAILABLE", "stale": True, "peers": []},
                status_code=503,
            )

    @app.get("/api/devices/{device_id}")
    async def detail(device_id: UUID, request: Request):
        value = session(request)
        return await remote("GET", "/api/v1/admin/devices/" + str(device_id), value["token"])

    @app.post("/api/customers")
    async def customer(request: Request):
        value = session(request, True)
        return await remote("POST", "/api/v1/admin/customers", value["token"], await request.json())

    @app.post("/api/devices")
    async def device_create(request: Request):
        value = session(request, True)
        return await remote("POST", "/api/v1/admin/devices", value["token"], await request.json())

    @app.patch("/api/{entity}/{entity_id}")
    async def edit(entity: str, entity_id: UUID, request: Request):
        if entity not in {"customers", "devices"}:
            raise HTTPException(404, "İşlem bulunamadı.")
        value = session(request, True)
        return await remote("PATCH", f"/api/v1/admin/{entity}/{entity_id}", value["token"], await request.json())

    @app.post("/api/licenses")
    async def license_create(request: Request):
        value = session(request, True)
        return await remote("POST", "/api/v1/admin/licenses", value["token"], await request.json())

    @app.post("/api/actions/{entity}/{entity_id}/{action}")
    async def action(entity: str, entity_id: UUID, action: str, request: Request):
        allowed = {
            "devices": {"approve", "suspend", "revoke", "reassign", "archive", "restore"},
            "customers": {"archive", "restore"},
            "licenses": {"renew", "suspend", "resume", "revoke"},
        }
        if entity not in allowed or action not in allowed[entity]:
            raise HTTPException(404, "İşlem bulunamadı.")
        value = session(request, True)
        return await remote(
            "POST",
            f"/api/v1/admin/{entity}/{entity_id}/{action}",
            value["token"],
            await request.json(),
        )

    if Path(cfg.static_directory).is_dir():
        app.mount("/", StaticFiles(directory=cfg.static_directory, html=True), name="frontend")
    return app


app = create_app()
