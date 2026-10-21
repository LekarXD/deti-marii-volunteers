from contextlib import asynccontextmanager
from fastapi import FastAPI
from pydantic import BaseModel, Field
from app.core.config import get_settings
from app.core.db import engine
from app.core.model_loader import load_models
from app.core.platform import install_platform
from app.modules.assets.router import router as assets
from app.modules.auth.router import router as auth
from app.modules.staff.router import router as staff
from app.modules.applications.router import router as applications
from app.modules.interviews.router import router as interviews
from app.modules.activities.router import router as activities
from app.modules.participants.router import router as participants
from app.modules.learning.router import router as learning
from app.modules.messaging.router import router as messaging
from app.modules.crm.router import router as crm
from app.modules.knowledge.router import router as knowledge
from app.modules.followups.router import router as followups
from app.modules.notifications.router import router as notifications
from app.modules.notifications.telegram_router import router as telegram
from app.modules.studio.router import router as studio
from app.modules.profile.router import router as profile
from app.modules.simulator.router import router as simulator
from app.modules.recordings.router import router as recordings
from app.modules.reporting.router import router as reporting
from app.modules.admin.router import router as admin
from app.modules.dobro.router import router as dobro
from app.modules.participants.access import get_assignment_access
from app.modules.activities.assignment_service import ActivityAssignmentAccess

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
    app.dependency_overrides[get_assignment_access] = lambda: ActivityAssignmentAccess()
    for router in (auth, staff, assets, applications, interviews, participants, learning, messaging, crm, knowledge, followups, notifications, studio, profile, simulator, recordings, reporting, admin, dobro, telegram):
        app.include_router(router)
    app.include_router(activities, prefix="/api/v1")
    return app

app = create_app()
