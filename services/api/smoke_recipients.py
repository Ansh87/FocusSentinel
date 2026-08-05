"""Smoke test for the notification-recipients endpoints: membership checks
(previously missing entirely), the new PATCH/DELETE, and FK safety when
deleting a recipient that already has notification history against it.
"""
import os

os.environ["DATABASE_URL"] = f"sqlite:///{os.path.expanduser('~')}/smoke_recipients.db"
db_path = os.path.expanduser("~/smoke_recipients.db")
if os.path.exists(db_path):
    os.remove(db_path)

from sqlalchemy import event  # noqa: E402
from app.database import Base, engine  # noqa: E402


@event.listens_for(engine, "connect")
def _enable_fk(dbapi_connection, connection_record):
    dbapi_connection.execute("PRAGMA foreign_keys=ON")


from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app import models  # noqa: E402
from app.notifications import enqueue_notification  # noqa: E402

Base.metadata.create_all(bind=engine)
client = TestClient(app)


def register_and_login(email, password, display_name, role="parent"):
    r = client.post("/auth/register", json={"email": email, "password": password, "display_name": display_name, "role": role})
    assert r.status_code in (200, 201), r.text
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


headers_a = register_and_login("recipA@example.com", "password123", "Parent A")
r = client.post("/families", json={"name": "Family A", "timezone": "UTC"}, headers=headers_a)
family_a = r.json()["id"]

headers_b = register_and_login("recipB@example.com", "password123", "Parent B")
r = client.post("/families", json={"name": "Family B", "timezone": "UTC"}, headers=headers_b)
family_b = r.json()["id"]

# --- Parent B cannot create or list recipients for Parent A's family ---
r = client.post(
    "/notification-recipients",
    json={"family_id": family_a, "name": "Intruder", "relationship": "parent", "email": "x@example.com"},
    headers=headers_b,
)
assert r.status_code == 403, r.text
r = client.get(f"/notification-recipients/family/{family_a}", headers=headers_b)
assert r.status_code == 403, r.text
print("Cross-family create/list blocked: OK")

# --- Parent A adds themself as an SMS-opted-in recipient ---
r = client.post(
    "/notification-recipients",
    json={
        "family_id": family_a,
        "name": "Parent A",
        "relationship": "parent",
        "email": "recipA@example.com",
        "mobile_number": "(555) 111-2222",
        "preferred_channels": ["email", "sms"],
        "severity_preference": "all",
    },
    headers=headers_a,
)
assert r.status_code == 201, r.text
recipient = r.json()
assert recipient["mobile_number"] == "+15551112222", recipient
assert recipient["preferred_channels"] == ["email", "sms"], recipient
print("Create recipient with normalized mobile number: OK")

r = client.get(f"/notification-recipients/family/{family_a}", headers=headers_a)
assert len(r.json()) == 1, r.json()
print("List recipients (own family): OK")

# --- Update it ---
r = client.patch(
    f"/notification-recipients/{recipient['id']}",
    json={"mobile_number": "555-333-4444", "preferred_channels": ["sms"]},
    headers=headers_a,
)
assert r.status_code == 200, r.text
assert r.json()["mobile_number"] == "+15553334444", r.json()
assert r.json()["preferred_channels"] == ["sms"], r.json()
print("Update recipient (renormalizes new number): OK")

# --- Parent B cannot edit/delete Parent A's recipient ---
r = client.patch(f"/notification-recipients/{recipient['id']}", json={"name": "Hijacked"}, headers=headers_b)
assert r.status_code == 403, r.text
r = client.delete(f"/notification-recipients/{recipient['id']}", headers=headers_b)
assert r.status_code == 403, r.text
print("Cross-family update/delete blocked: OK")

# --- Give this recipient some notification history, then delete them (FK safety) ---
with SessionLocal() as db:
    fam = db.get(models.Family, family_a)
    student = models.Student(family_id=family_a, display_name="Kid", age_range="8_12", timezone="UTC")
    db.add(student)
    db.flush()
    enqueue_notification(db, family_id=family_a, student_id=student.id, event_type="restricted", rule_id=None, payload={})
    db.commit()

r = client.delete(f"/notification-recipients/{recipient['id']}", headers=headers_a)
assert r.status_code == 200, r.text
print("Delete recipient with existing notification history (FK-safe): OK")

r = client.get(f"/notification-recipients/family/{family_a}", headers=headers_a)
assert len(r.json()) == 0, r.json()
print("Recipient list empty after delete: OK")

print("\nALL SMOKE_RECIPIENTS CHECKS PASSED")
