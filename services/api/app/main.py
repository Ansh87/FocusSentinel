from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import Base, engine
from .routers import (
    audit_log,
    auth,
    demo,
    device_health,
    devices,
    extension_requests,
    families,
    notification_recipients,
    rules,
    students,
    usage_events,
    websites,
)

# For this Phase 1 build, SQLAlchemy's create_all is the actual schema source
# for both SQLite (tests/local dev) and the Postgres container in
# docker-compose.yml — see the comment on the `postgres` service there for why
# database/migrations/0001_init.sql (which uses Postgres ARRAY/JSONB types) is
# a documentation reference rather than something auto-applied alongside this.
# A real deployment should switch to Alembic-managed migrations (included in
# requirements.txt) before this diverges further from the ORM models.
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="FocusSentinel API",
    description="Backend API for FocusSentinel — see /docs for the interactive OpenAPI spec.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(families.router)
app.include_router(students.router)
app.include_router(devices.router)
app.include_router(usage_events.router)
app.include_router(rules.router)
app.include_router(websites.router)
app.include_router(extension_requests.router)
app.include_router(notification_recipients.router)
app.include_router(device_health.router)
app.include_router(audit_log.router)
app.include_router(demo.router)


@app.get("/health")
def health():
    return {"status": "ok", "environment": settings.environment}
