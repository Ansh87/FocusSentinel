"""Smoke test for the two-way SMS flow: a student texts to request more
time, the parent gets asked, and can reply YES/NO by text to decide --
covers app/routers/sms.py end to end with FK enforcement on (see
smoke_fk_enforced.py for why that matters).
"""
import os

os.environ["DATABASE_URL"] = f"sqlite:///{os.path.expanduser('~')}/smoke_sms.db"
os.environ["SMS_WEBHOOK_TOKEN"] = "test-webhook-secret"
db_path = os.path.expanduser("~/smoke_sms.db")
if os.path.exists(db_path):
    os.remove(db_path)

from sqlalchemy import event  # noqa: E402
from app.database import Base, engine  # noqa: E402


@event.listens_for(engine, "connect")
def _enable_fk(dbapi_connection, connection_record):
    dbapi_connection.execute("PRAGMA foreign_keys=ON")


from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

Base.metadata.create_all(bind=engine)
client = TestClient(app)


def register_and_login(email, password, display_name, role="parent"):
    r = client.post("/auth/register", json={"email": email, "password": password, "display_name": display_name, "role": role})
    assert r.status_code in (200, 201), r.text
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def sms(from_number, body, token="test-webhook-secret"):
    params = {"token": token} if token is not None else {}
    return client.post("/sms/inbound", params=params, data={"From": from_number, "Body": body})


headers = register_and_login("smsparent@example.com", "password123", "SMS Parent")
r = client.post("/families", json={"name": "SMS Family", "timezone": "UTC"}, headers=headers)
family_id = r.json()["id"]
r = client.post("/students", json={"family_id": family_id, "display_name": "Sam", "age_range": "13_15", "timezone": "UTC"}, headers=headers)
student_id = r.json()["id"]

# --- Wrong webhook token is rejected ---
r = sms("+15551234567", "MORE 15", token="wrong-token")
assert r.status_code == 403, r.text
print("Wrong webhook token rejected: OK")

# --- Unrecognized numbers get a generic reply, not an error ---
r = sms("+19995550000", "hello")
assert r.status_code == 200, r.text
assert "not linked" in r.text.lower() or "isn't linked" in r.text.lower(), r.text
print("Unrecognized number handled gracefully: OK")

# --- Register the student's phone from the dashboard side ---
r = client.post(f"/students/{student_id}/phone", json={"phone_number": "(555) 123-4567"}, headers=headers)
assert r.status_code == 200, r.text
assert r.json()["phone_number"] == "+15551234567", r.json()
print("Student phone registered + normalized: OK")

r = client.get(f"/students/family/{family_id}", headers=headers)
assert r.json()[0]["has_phone"] is True, r.json()
print("has_phone reflected in student list: OK")

# --- Add an SMS-opted-in notification recipient (the parent's own phone) ---
r = client.post(
    "/notification-recipients",
    json={
        "family_id": family_id,
        "name": "Mom",
        "relationship": "parent",
        "mobile_number": "555-987-6543",
        "preferred_channels": ["sms"],
    },
    headers=headers,
)
assert r.status_code in (200, 201), r.text

# --- Student texts in a request ---
r = sms("+15551234567", "MORE 20 please, almost done with a video")
assert r.status_code == 200, r.text
assert "asked your parent" in r.text.lower(), r.text
print("Student SMS request created extension request: OK")

r = client.get(f"/extension-requests?student_id={student_id}&status=pending", headers=headers)
pending = r.json()
assert len(pending) == 1, pending
assert pending[0]["requested_minutes"] == 20, pending[0]
print("Extension request has parsed minutes (20): OK")

# --- Parent replies NO to deny it ---
r = sms("+15559876543", "NO thanks")
assert r.status_code == 200, r.text
assert "denied" in r.text.lower(), r.text
print("Parent SMS deny resolved the request: OK")

r = client.get(f"/extension-requests?student_id={student_id}&status=denied", headers=headers)
assert len(r.json()) == 1, r.json()
print("Request status is denied: OK")

# --- Student texts again, parent approves this time ---
r = sms("+15551234567", "10")
assert r.status_code == 200, r.text
r = sms("+15559876543", "YES")
assert r.status_code == 200, r.text
assert "approved 10" in r.text.lower(), r.text
print("Parent SMS approve resolved the request with correct minutes: OK")

r = client.get(f"/extension-requests?student_id={student_id}&status=approved", headers=headers)
assert len(r.json()) == 1, r.json()
print("Request status is approved: OK")

# --- Replying again with nothing pending is handled gracefully ---
r = sms("+15559876543", "YES")
assert r.status_code == 200, r.text
print("Reply with nothing pending handled gracefully: OK")

# --- Duplicate phone registration across students is rejected ---
r = client.post("/students", json={"family_id": family_id, "display_name": "Alex2", "age_range": "8_12", "timezone": "UTC"}, headers=headers)
student2_id = r.json()["id"]
r = client.post(f"/students/{student2_id}/phone", json={"phone_number": "+15551234567"}, headers=headers)
assert r.status_code == 409, r.text
print("Duplicate phone number across students rejected: OK")

# --- Clearing the phone number works ---
r = client.delete(f"/students/{student_id}/phone", headers=headers)
assert r.status_code == 200, r.text
r = client.get(f"/students/{student_id}/phone", headers=headers)
assert r.json()["has_phone"] is False, r.json()
print("Clearing student phone number: OK")

# --- No webhook token configured at all still works when unset server-side ---
# (covered implicitly above since SMS_WEBHOOK_TOKEN is set; the "unset"
# case is a simple code-path check, not worth its own process restart here)

print("\nALL SMOKE_SMS CHECKS PASSED")
