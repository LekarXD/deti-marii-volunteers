from uuid import uuid4
from fastapi import FastAPI, Request
from sqlalchemy import text
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.errors import ApiError, install_error_handlers

def install_platform(app: FastAPI):
    # The trusted gateway strips this path before forwarding. Never trust X-Forwarded-Prefix.
    app.root_path = get_settings().app_mount_prefix
    install_error_handlers(app)
    @app.middleware("http")
    async def request_metadata(request: Request, call_next):
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response
    @app.get("/health", operation_id="health")
    async def health():
        return {"status": "ok"}
    @app.get("/ready", operation_id="readiness")
    async def ready():
        async with SessionLocal() as db:
            await db.execute(text("SELECT 1 FROM alembic_version"))
        return {"status": "ready"}
    @app.get("/version.json", operation_id="version")
    async def version():
        return {"release": get_settings().release}
