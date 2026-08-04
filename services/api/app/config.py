import json

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./focussentinel.db"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30
    password_reset_expire_minutes: int = 30

    # Base URL of the deployed web-dashboard, used to build the link inside
    # password-reset emails (e.g. "https://web-dashboard-production-xxxx.up.railway.app").
    # Falls back to localhost for local dev.
    frontend_base_url: str = "http://localhost:3000"

    device_token_bytes: int = 32

    # Notification provider selection — adapters live in
    # services/notification-worker/app/adapters. Values other than the
    # 'console' defaults require real credentials and are never read from
    # client code.
    email_provider: str = "console"
    sms_provider: str = "console"

    cors_origins: list[str] = ["http://localhost:3000"]

    environment: str = "development"

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, v: str) -> str:
        # Managed Postgres providers (Railway, Render, Heroku, etc.) hand out
        # a plain `postgres://` or `postgresql://` URL. SQLAlchemy needs the
        # psycopg3 driver explicitly named, so this rewrites the scheme
        # instead of requiring every deployment to hand-edit the string.
        if v.startswith("postgres://"):
            return "postgresql+psycopg://" + v[len("postgres://"):]
        if v.startswith("postgresql://"):
            return "postgresql+psycopg://" + v[len("postgresql://"):]
        return v

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v):
        # Accepts either a JSON array (`["https://a.com","https://b.com"]`)
        # or a plain comma-separated string (`https://a.com,https://b.com`),
        # since it's easy to paste the latter into a platform's env var UI
        # without thinking about JSON quoting.
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):
                return json.loads(v)
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v


settings = Settings()
