import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from backend.app.api.routes import router
from backend.app.api.connections import router as connections_router
from backend.app.api.serial import router as serial_router
from backend.app.api.storage import router as storage_router
from backend.app.logging import configure_logging

configure_logging()
logger = logging.getLogger("kronoskvm.api")


def create_app() -> FastAPI:
    application = FastAPI(
        title="KronosKVM API",
        version="0.1.0",
        description="Local control-plane API for the KronosKVM prototype.",
    )

    @application.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        started = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "Unhandled request error",
                extra={"request_id": request_id},
            )
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error", "request_id": request_id},
                headers={"x-request-id": request_id},
            )
        elapsed_ms = round((time.monotonic() - started) * 1000, 1)
        response.headers["x-request-id"] = request_id
        logger.info(
            "%s %s %s %.1fms",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            extra={"request_id": request_id},
        )
        return response

    application.include_router(router)
    application.include_router(connections_router)
    application.include_router(serial_router)
    application.include_router(storage_router)
    return application


app = create_app()
