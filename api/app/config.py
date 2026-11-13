from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

API_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: str = "development"
    # Neon / Postgres connection string, e.g.
    # postgresql://user:pass@ep-xxx.ap-southeast-1.aws.neon.tech/executive_admin?sslmode=require
    # When unset in development, a local SQLite file is used so records still persist.
    database_url: str | None = None
    cors_origins: list[str] = ["http://localhost:3000"]
    upload_dir: Path = API_ROOT / "uploads"
    max_upload_mb: int = 10
    max_attachments_per_record: int = 10
    # Seconds between automatic SLA escalation sweeps (0 disables the background sweep).
    escalation_interval_s: int = 300

    # ---- sign-in (production: email + password until One Admin) ----
    # The public address, e.g. https://ea.bishnoi.ai. State-changing requests must come from it.
    public_origin: str | None = None
    session_idle_hours: int = 12  # signed out after this long without activity
    session_max_days: int = 14  # and in any case after this long
    login_max_failures: int = 5  # wrong passwords before the account locks
    login_lock_minutes: int = 15
    # First Admin, created at startup when no Admin can sign in yet. Must change the password on first sign-in.
    bootstrap_admin_email: str | None = None
    bootstrap_admin_name: str = "Executive Admin"
    bootstrap_admin_password: str | None = None
    bootstrap_company_code: str = "GPI"

    @property
    def is_dev(self) -> bool:
        return self.env == "development"

    @property
    def cookie_secure(self) -> bool:
        return not self.is_dev

    @property
    def effective_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        if self.is_dev:
            return f"sqlite+aiosqlite:///{(API_ROOT / 'executive_admin.db').as_posix()}"
        raise RuntimeError("DATABASE_URL is required outside development")


@lru_cache
def get_settings() -> Settings:
    return Settings()
