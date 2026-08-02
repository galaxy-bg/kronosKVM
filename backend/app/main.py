import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from backend.app.api.connections import router as connections_router
from backend.app.api.hid import router as hid_router
from backend.app.api.logs import router as logs_router
from backend.app.api.network_settings import router as network_settings_router
from backend.app.api.routes import router
from backend.app.api.serial import router as serial_router
from backend.app.api.session_logs import router as session_logs_router
from backend.app.api.ssh import router as ssh_router
from backend.app.api.storage import router as storage_router
from backend.app.api.tasks import router as tasks_router
from backend.app.api.video import router as video_router
from backend.app.logging import audit, configure_logging
from backend.app.services.storage import cleanup_incomplete_uploads
from backend.app.services.tasks import finish_task, start_task

configure_logging()
logger = logging.getLogger("kronoskvm.api")


def create_app() -> FastAPI:
    application = FastAPI(
        title="KronosKVM API",
        version="0.1.0",
        description="Local control-plane API for the KronosKVM prototype.",
    )

    @application.on_event("startup")
    async def cleanup_storage_fragments() -> None:
        removed = cleanup_incomplete_uploads()
        if removed:
            audit("storage.fragments.cleaned", count=len(removed), fragments=removed)

    @application.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        started = time.monotonic()
        task = None
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not request.url.path.startswith(
            "/api/v1/tasks"
        ):
            requested_task_id = request.headers.get("x-kronos-task-id")
            if requested_task_id:
                try:
                    requested_task_id = str(uuid.UUID(requested_task_id))
                except ValueError:
                    requested_task_id = None
            task = start_task(
                operation=f"http.{request.method.lower()}",
                title=f"{request.method} {request.url.path}",
                task_id=requested_task_id,
                detail=request.url.path,
                source="api",
            )
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "Unhandled request error",
                extra={"request_id": request_id},
            )
            if task:
                finish_task(task["id"], False, "Unhandled API error")
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error", "request_id": request_id},
                headers={"x-request-id": request_id},
            )
        elapsed_ms = round((time.monotonic() - started) * 1000, 1)
        response.headers["x-request-id"] = request_id
        if task:
            response.headers["x-kronos-task-id"] = task["id"]
            finish_task(
                task["id"],
                response.status_code < 400,
                None if response.status_code < 400 else f"HTTP {response.status_code}",
            )
        logger.info(
            "%s %s %s %.1fms",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            extra={"request_id": request_id},
        )
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            audit(
                "http.mutation",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                client=request.client.host if request.client else None,
                duration_ms=elapsed_ms,
            )
        return response

    application.include_router(router)
    application.include_router(connections_router)
    application.include_router(serial_router)
    application.include_router(session_logs_router)
    application.include_router(hid_router)
    application.include_router(logs_router)
    application.include_router(network_settings_router)
    application.include_router(ssh_router)
    application.include_router(storage_router)
    application.include_router(tasks_router)
    application.include_router(video_router)
    return application


app = create_app()
