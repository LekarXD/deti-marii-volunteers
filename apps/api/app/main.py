from contextlib import asynccontextmanager
from fastapi import FastAPI
from pydantic import BaseModel, Field
from app.core.config import get_settings
from app.core.db import engine
from app.core.model_loader import load_models
from app.core.platform import install_platform
from app.modules.auth.router import router as auth
from app.modules.staff.router import router as staff
from app.modules.applications.router import router as applications
from app.modules.interviews.router import router as interviews
from app.modules.activities.router import router as activities
from app.modules.participants.router import router as participants
from app.modules.learning.router import router as learning

class ErrorView(BaseModel):
    code: str
    message: str
    field_errors: dict[str, str] = Field(default_factory=dict)
    current_version: int | None = None
    retryable: bool = False
    request_id: str | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    get_settings().validate_runtime()
    load_models()
    yield
    await engine.dispose()

def create_app() -> FastAPI:
    app = FastAPI(title="Опора API", version="0.1.0", lifespan=lifespan,
                  responses={status: {"model": ErrorView} for status in (400, 401, 403, 404, 409, 422, 429, 503)})
    install_platform(app)
    for router in (auth, staff, applications, interviews, participants, learning):
        app.include_router(router)
    app.include_router(activities, prefix="/api/v1")
    return app

app = create_app()
