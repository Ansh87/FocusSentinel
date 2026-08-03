from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///../api/focussentinel.db"
    redis_url: str = "redis://localhost:6379/0"

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, v: str) -> str:
        # Same rewrite as services/api/app/config.py — managed Postgres
        # providers hand out `postgres://`/`postgresql://`; SQLAlchemy here
        # needs the psycopg3 driver named explicitly.
        if v.startswith("postgres://"):
            return "postgresql+psycopg://" + v[len("postgres://"):]
        if v.startswith("postgresql://"):
            return "postgresql+psycopg://" + v[len("postgresql://"):]
        return v

    email_provider: str = "console"   # console | smtp | sendgrid | ses | resend
    sms_provider: str = "console"     # console | twilio

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_address: str = "no-reply@focussentinel.example"

    sendgrid_api_key: str = ""
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""

    poll_interval_seconds: float = 2.0


settings = Settings()
