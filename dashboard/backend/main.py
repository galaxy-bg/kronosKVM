"""Same-origin dashboard gateway; upstream credentials stay in expiring server sessions."""

import secrets
import sqlite3
import asyncio
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
from .tasks import TaskStore, operation

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
    task_database: str = ":memory:"
    static_directory: str = str(Path(__file__).resolve().parents[1] / "frontend/dist")


class Login(BaseModel):
    token: SecretStr = Field(min_length=32, max_length=200)


def create_app(settings=None, upstream=None):
    cfg = settings or Settings()
    sessions = {}
    deleted_peers = {}
    attempts = defaultdict(deque)
    vpn_reader = Reader(cfg)
    origins = {v.strip().rstrip("/") for v in cfg.allowed_origins.split(",")}

    @asynccontextmanager
    async def lifespan(app):
        app.state.tasks = TaskStore(cfg.task_database)
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
        app.state.tasks.close()

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
                        {"detail": "Request origin is not allowed."}, status_code=403
                    )
                chunks = []
                size = 0
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > 16384:
                        return JSONResponse({"detail": "Request is too large."}, status_code=413)
                    chunks.append(chunk)
                request._body = b"".join(chunks)
        task_id = None
        try:
            spec = operation(request.method, request.url.path)
        except ValueError:
            spec = None
        if spec:
            try:
                value = session(request, True)
                task_id = app.state.tasks.start(*spec[:2], value["actor"]["name"], spec[2])
            except HTTPException as error:
                return JSONResponse({"detail":error.detail},status_code=error.status_code,headers={"Cache-Control":"no-store"})
            except (OSError,sqlite3.Error):
                return JSONResponse({"detail":"Task history is unavailable. No action was started."},status_code=503,headers={"Cache-Control":"no-store"})
        try:
            response = await call_next(request)
        except BaseException as error:
            if task_id:
                try:app.state.tasks.finish(task_id,"unknown",None,"Outcome not confirmed. Review the current record before retrying.")
                except (OSError,sqlite3.Error):pass
            if isinstance(error,asyncio.CancelledError):raise
            if not isinstance(error,Exception):raise
            response = JSONResponse({"detail":"Operation outcome could not be confirmed. Review the current state."},status_code=500)
        if task_id:
            code=response.status_code
            state="successful" if code<400 else "unknown" if code>=500 else "failed"
            reasons={401:"Session no longer authorized.",403:"Permission denied.",404:"Record or action not found.",409:"Record state changed. Review it before retrying.",422:"Request validation failed. Review the form fields.",429:"Request limit reached. Retry later."}
            reason=None if state=="successful" else "Outcome not confirmed. Review the current record before retrying." if state=="unknown" else reasons.get(code,"Request was rejected.")
            try:app.state.tasks.finish(task_id,state,code,reason)
            except (OSError,sqlite3.Error):response.headers["X-KDX-Task-Status"]="unknown"
            response.headers["X-KDX-Task-ID"]=task_id
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
            raise HTTPException(503, "Registration connection requires HTTPS.")
        try:
            response = await app.state.upstream.request(
                method, path, headers={"Authorization": "Bearer " + token}, json=payload
            )
        except httpx.RequestError:
            raise HTTPException(
                503, "Registration Server is unavailable. Try again."
            ) from None
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail")
                if not isinstance(detail, str):
                    detail = "Request validation failed."
            except ValueError:
                detail = "Registration request failed."
            raise HTTPException(response.status_code if response.status_code < 500 else 502, detail)
        if response.is_redirect:
            raise HTTPException(502, "Unexpected Registration redirect.")
        return response.json()

    def session(request, mutation=False):
        sid = request.cookies.get(COOKIE, "")
        value = sessions.get(sid)
        if not value or value["until"] <= time.time():
            sessions.pop(sid, None)
            raise HTTPException(401, "Session expired. Sign in again.")
        if mutation:
            if value["actor"]["role"] != "admin":
                raise HTTPException(403, "This action requires administrator access.")
            if not secrets.compare_digest(request.headers.get("x-csrf-token", ""), value["csrf"]):
                raise HTTPException(403, "Request verification failed. Refresh the page.")
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
                raise HTTPException(429, "Too many sign-in attempts. Try again later.")
        bucket = attempts[ip]
        while bucket and bucket[0] < tick - 900:
            bucket.popleft()
        if len(bucket) >= 10:
            raise HTTPException(429, "Too many sign-in attempts. Wait 15 minutes.")
        bucket.append(tick)
        token = value.token.get_secret_value()
        actor = await remote("GET", "/api/v1/admin/session", token)
        sessions.pop(request.cookies.get(COOKIE, ""), None)
        for sid in list(sessions):
            if sessions[sid]["until"] <= tick:
                del sessions[sid]
        if len(sessions) >= 1000:
            raise HTTPException(503, "Session capacity reached.")
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
            raise HTTPException(403, "Request validation failed.")
        sessions.pop(request.cookies.get(COOKIE, ""), None)
        response = JSONResponse({"ok": True})
        response.delete_cookie(COOKIE, path="/")
        return response

    @app.get("/api/tasks")
    async def task_list(request: Request):
        value = session(request)
        await remote("GET", "/api/v1/admin/session", value["token"])
        return app.state.tasks.list()

    @app.get("/api/tasks/{task_id}")
    async def task_detail(task_id: UUID, request: Request):
        value = session(request)
        await remote("GET", "/api/v1/admin/session", value["token"])
        item = app.state.tasks.detail(str(task_id))
        if not item:raise HTTPException(404,"Task not found.")
        return item

    @app.delete("/api/tasks/completed")
    async def task_clear(request: Request):
        value = session(request, True)
        actor = await remote("GET", "/api/v1/admin/session", value["token"])
        if actor["role"]!="admin":raise HTTPException(403,"Administrator access required.")
        return {"cleared":app.state.tasks.clear()}

    @app.post("/api/tasks/events")
    async def task_event(request: Request):
        value=session(request,True)
        actor=await remote("GET","/api/v1/admin/session",value["token"])
        if actor["role"]!="admin":raise HTTPException(403,"Administrator access required.")
        try:event=await request.json()
        except ValueError:raise HTTPException(422,"Invalid task event.") from None
        if not isinstance(event,dict) or set(event)!={"kind","target"} or not isinstance(event["kind"],str) or event["kind"] not in {"vpn_config_download","activation_token_copy"}:
            raise HTTPException(422,"Invalid task event.")
        try:target=str(UUID(event["target"]))
        except (ValueError,TypeError,AttributeError):raise HTTPException(422,"Invalid task target.") from None
        title={"vpn_config_download":"Request VPN configuration download","activation_token_copy":"Request activation token copy"}[event["kind"]]
        ident=app.state.tasks.start(event["kind"],title,actor["name"],target)
        app.state.tasks.finish(ident,"successful",200)
        return {"task_id":ident}

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
            result = await vpn_reader.read(devices)
            clients = await remote("GET", "/api/v1/admin/vpn-clients", value["token"])
            by_key = {item["public_key"]: item for item in clients}
            for peer in result.get("peers", []):
                client = by_key.get(peer.get("public_key"))
                if client:
                    peer["client"] = {k:client.get(k) for k in ("id","name","owner_name","platform","customer","status")}
            peers = result.get("peers", [])
            tick = time.monotonic()
            for key in list(deleted_peers):
                if deleted_peers[key]["until"] <= tick:
                    del deleted_peers[key]
            result["peers"] = [p for p in peers if not (
                p["public_key"] in deleted_peers and
                result.get("sampled_at", 0) <= deleted_peers[p["public_key"]]["at"] + 1)]
            if isinstance(result.get("totals"), dict):
                kept = result["peers"]
                result["totals"].update(peers=len(kept),
                    recent=sum(p.get("connection_state")=="recent" for p in kept),
                    matched=sum(bool(p.get("device")) for p in kept),
                    received_bytes=sum(p.get("received_bytes",0) for p in kept),
                    sent_bytes=sum(p.get("sent_bytes",0) for p in kept))
            return result
        except (OSError, ValueError, TypeError, KeyError, TimeoutError):
            return JSONResponse(
                {"configured": True, "error": "VPN_STATUS_UNAVAILABLE", "stale": True, "peers": []},
                status_code=503,
            )

    @app.post("/api/vpn/peers/delete")
    async def vpn_peer_delete(request: Request):
        value = session(request, True)
        payload = await request.json()
        result = await remote("POST", "/api/v1/admin/vpn-peers/delete", value["token"], payload)
        if result.get("status") != "DELETED":
            raise HTTPException(502, "VPN peer deletion could not be confirmed.")
        # Suppress only older samples for 90 seconds, not a genuinely re-added peer.
        deleted_peers[payload["public_key"]] = {"at":time.time(), "until":time.monotonic()+90}
        vpn_reader.raw = None
        vpn_reader.cached_at = 0
        return result

    @app.get("/api/vpn/requests")
    async def vpn_requests(request: Request):
        value = session(request)
        return await remote("GET", "/api/v1/admin/vpn", value["token"])

    @app.get("/api/vpn/clients")
    async def vpn_clients(request: Request):
        value = session(request)
        return await remote("GET", "/api/v1/admin/vpn-clients", value["token"])

    @app.post("/api/vpn/clients")
    async def vpn_client_create(request: Request):
        value = session(request, True)
        return await remote("POST", "/api/v1/admin/vpn-clients", value["token"], await request.json())

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
            raise HTTPException(404, "Action not found.")
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
            "vpn": {"approve", "suspend", "resume", "delete", "archive"},
            "vpn-clients": {"suspend", "resume", "delete"},
            "licenses": {"renew", "suspend", "resume", "revoke"},
        }
        if entity not in allowed or action not in allowed[entity]:
            raise HTTPException(404, "Action not found.")
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
