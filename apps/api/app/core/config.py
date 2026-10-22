from functools import lru_cache
from uuid import UUID
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from app.core.paths import normalize_mount_prefix

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OPORA_", env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://opora:opora@127.0.0.1:5432/opora"
    environment: str = "development"
    foundation_id: UUID = UUID("00000000-0000-0000-0000-000000000001")
    trusted_origins: list[str] = ["http://127.0.0.1:5173", "http://localhost:5173", "http://127.0.0.1:5174", "http://localhost:5174", "http://testserver"]
    app_mount_prefix: str = ""
    @field_validator("app_mount_prefix", mode="before")
    @classmethod
    def valid_mount_prefix(cls,value):return normalize_mount_prefix(value)
    cookie_secure: bool = False
    secret_key: str = "development-only-set-OPORA_SECRET_KEY"
    release: str = "development"
    asset_root: str = "/tmp/opora-assets"
    max_asset_bytes: int = 10 * 1024 * 1024
    demo_email_codes: bool = False
    # Per-IP auth limits key on request.client.host; behind a proxy that is not trusted to forward
    # the visitor's address that is the proxy itself, i.e. one platform-wide bucket. Enable only then.
    client_ip_rate_limits: bool = False
    dev_inbox: bool = True
    session_hours: int = 24
    worker_kinds: list[str] = ["outbox.deliver"]
    email_webhook_secret: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_from: str | None = None
    smtp_starttls: bool = True
    smtp_username: str | None = None
    smtp_password: str | None = None
    def validate_runtime(self):
        if self.demo_email_codes and self.environment not in ("development", "staging"):
            raise RuntimeError("Demo email codes are forbidden outside development/staging")
        if self.environment != "development" and (not self.cookie_secure or self.secret_key.startswith("development-") or self.dev_inbox):
            raise RuntimeError("Production requires secure cookies, configured encryption secret, disabled dev inbox")
        if not self.database_url.startswith("postgresql+psycopg://"):
            raise RuntimeError("PostgreSQL with psycopg is required")

@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_runtime()
    return settings
