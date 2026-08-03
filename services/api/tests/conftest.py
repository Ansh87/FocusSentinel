import os
import sys
from datetime import datetime, timedelta

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_focussentinel.db")
os.environ.setdefault("JWT_SECRET", "test-secret")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app import models

TEST_DB_PATH = "./test_focussentinel.db"
engine = create_engine(f"sqlite:///{TEST_DB_PATH}", connect_args={"check_same_thread": False})


# Same SAVEPOINT workaround as app/database.py — this test engine is separate
# from the app's own engine, so it needs the fix applied independently. This
# is what lets db.begin_nested() in usage_events.py isolate a single
# duplicate-key failure inside a batch without rolling back the whole request.
@event.listens_for(engine, "connect")
def _sqlite_disable_pysqlite_txn(dbapi_connection, connection_record):
    dbapi_connection.isolation_level = None
    # WAL mode (see app/database.py for the full explanation) — without this,
    # the db_session fixture holding a read open across several client.post()
    # calls in the same test can make the app's own write connection fail
    # with "database is locked".
    dbapi_connection.execute("PRAGMA journal_mode=WAL")
    dbapi_connection.execute("PRAGMA busy_timeout=5000")


@event.listens_for(engine, "begin")
def _sqlite_emit_begin(conn):
    conn.exec_driver_sql("BEGIN")


TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="function", autouse=True)
def fresh_db():
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    categories = [
        ("games", "Games"),
        ("short_form_video", "Short-form video"),
        ("social_media", "Social media"),
        ("entertainment_video", "Entertainment video"),
        ("messaging", "Messaging"),
        ("educational", "Educational"),
    ]
    for key, label in categories:
        db.add(models.ActivityCategory(key=key, label=label))
    db.commit()
    db.close()
    yield
    engine.dispose()
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db_session():
    db = TestingSessionLocal()
    yield db
    db.close()


def register_and_login(client, email="parent@example.com", role="parent") -> str:
    client.post(
        "/auth/register",
        json={"email": email, "password": "supersecret1", "display_name": "Parent", "role": role},
    )
    resp = client.post("/auth/login", json={"email": email, "password": "supersecret1"})
    return resp.json()["access_token"]


def create_family_student(client, token) -> tuple[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    family = client.post("/families", json={"name": "Test Family", "timezone": "America/Chicago"}, headers=headers).json()
    student = client.post(
        "/students",
        json={"family_id": family["id"], "display_name": "Student One", "age_range": "13_15", "timezone": "America/Chicago"},
        headers=headers,
    ).json()
    return family["id"], student["id"]
