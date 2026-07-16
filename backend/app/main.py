from fastapi import FastAPI

from backend.app.api.routes import router

app = FastAPI(
    title="KronosKVM API",
    version="0.1.0",
    description="Local control-plane API for the KronosKVM prototype.",
)
app.include_router(router)
