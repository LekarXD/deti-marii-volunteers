from functools import lru_cache
from uuid import UUID
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OPORA_", env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://opora:opora@127.0.0.1:5432/opora"
    environment: str = "development"
    foundation_id: UUID = UUID("00000000-0000-0000-0000-000000000001")
    trusted_origins: list[str] = ["http://127.0.0.1:5173", "http://localhost:5173", "http://127.0.0.1:5174", "http://localhost:5174", "http://testserver"]
    cookie_secure: bool = False
    secret_key: str = "development-only-set-OPORA_SECRET_KEY"
    release: str = "development"
    asset_root: str = "/tmp/opora-assets"
    max_asset_bytes: int = 10 * 1024 * 1024
    dev_inbox: bool = True
    session_hours: int = 24
    worker_kinds: list[str] = ["outbox.deliver"]
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_from: str | None = None
    smtp_starttls: bool = True
    smtp_username: str | None = None
    smtp_password: str | None = None
    def validate_runtime(self):
        if self.environment != "development" and (not self.cookie_secure or self.secret_key.startswith("development-") or self.dev_inbox):
            raise RuntimeError("Production requires secure cookies, configured encryption secret, disabled dev inbox")
        if not self.database_url.startswith("postgresql+psycopg://"):
            raise RuntimeError("PostgreSQL with psycopg is required")

@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_runtime()
    return settings
