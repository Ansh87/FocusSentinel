"""Smoke test for the email-based extension-request approve/deny flow that
replaced two-way SMS: creating a request queues an approval email (with
Approve/Deny links) to every parent in the family, and GET /extension-
requests/decide resolves the request from the token in those links without
requiring a login. Runs with FK enforcement on (see smoke_fk_enforced.py for
why that matters).
"""
import os

os.environ["DATABASE_URL"] = f"sqlite:///{os.path.expanduser('~')}/smoke_email_approval.db"
db_path = os.path.expanduser("~/smoke_email_approval.db")
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
from app.security import create_extension_action_token, decode_token  # noqa: E402

Base.metadata.create_all(bind=engine)
client = TestClient(app)


def register_and_login(email, password, display_name, role="parent"):
    r = client.post("/auth/register", json={"email": email, "password": password, "display_name": display_name, "role": role})
    assert r.status_code in (200, 201), r.text
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


headers = register_and_login("emailparent@example.com", "password123", "Email Parent")
r = client.post("/families", json={"name": "Email Family", "timezone": "UTC"}, headers=headers)
family_id = r.json()["id"]

r = client.post("/students", json={"family_id": family_id, "display_name": "Kid", "age_range": "8_12", "timezone": "UTC"}, headers=headers)
student_id = r.json()["id"]

r = client.post("/websites", json={"family_id": family_id, "domain": "roblox.com", "label": "Roblox", "category_key": "games"}, headers=headers)
assert r.status_code in (200, 201), r.text
website_id = r.json()["id"]

r = client.post(
    "/rules",
    json={
        "student_id": student_id,
        "name": "Games limit",
        "scope_type": "website",
        "website_ids": [website_id],
        "daily_limit_minutes": 30,
        "warning_one_at_minutes": 24,
    },
    headers=headers,
)
assert r.status_code in (200, 201), r.text
rule_id = r.json()["id"]

# --- Creating an extension request queues an approval email to the parent ---
r = client.post(
    "/extension-requests",
    json={"student_id": student_id, "rule_id": rule_id, "requested_minutes": 15, "reason_code": "friends"},
    headers=headers,
)
assert r.status_code == 201, r.text
request_id = r.json()["id"]

with SessionLocal() as db:
    email_event = (
        db.query(models.AccountEmailEvent)
        .filter_by(to_email="emailparent@example.com", event_type="extension_request_approval")
        .order_by(models.AccountEmailEvent.created_at.desc())
        .first()
    )
    assert email_event is not None, "approval email was not queued"
    assert "approve_url" in email_event.payload and "token=" in email_event.payload["approve_url"], email_event.payload
    print("Approval email queued with approve/deny links: OK")

# --- A bogus/garbage token is rejected with a friendly page, not a 500 ---
r = client.get("/extension-requests/decide", params={"token": "not-a-real-token", "action": "approve"})
assert r.status_code == 200, r.text
assert "invalid or has expired" in r.text
print("Garbage token handled gracefully: OK")

# --- Approving via the token resolves the request and lifts nothing needed
# here (no active restriction), but does flip status + decided_minutes ---
token = create_extension_action_token(request_id)
r = client.get("/extension-requests/decide", params={"token": token, "action": "approve"})
assert r.status_code == 200, r.text
assert "Approved" in r.text and "15" in r.text, r.text
print("Approve-by-token resolves the request: OK")

r = client.get(f"/extension-requests?student_id={student_id}", headers=headers)
approved = [x for x in r.json() if x["id"] == request_id][0]
assert approved["status"] == "approved", approved

# --- Clicking the same (or the deny) link again shows "already decided",
# doesn't flip the decision a second time ---
r = client.get("/extension-requests/decide", params={"token": token, "action": "deny"})
assert r.status_code == 200, r.text
assert "already" in r.text.lower(), r.text
print("Re-using a token after decision is a no-op: OK")

r = client.get(f"/extension-requests?student_id={student_id}", headers=headers)
still_approved = [x for x in r.json() if x["id"] == request_id][0]
assert still_approved["status"] == "approved", "a stale token must never flip an already-decided request"
print("Decision cannot be overturned by a stale token: OK")

# --- A second family's parent only gets emailed for their own family's
# requests, not this one ---
headers_b = register_and_login("otherparent@example.com", "password123", "Other Parent")
r = client.post("/families", json={"name": "Other Family", "timezone": "UTC"}, headers=headers_b)
family_b = r.json()["id"]
r = client.post("/students", json={"family_id": family_b, "display_name": "Other Kid", "age_range": "8_12", "timezone": "UTC"}, headers=headers_b)
student_b = r.json()["id"]
r = client.post(
    "/extension-requests",
    json={"student_id": student_b, "reason_code": "other"},
    headers=headers_b,
)
assert r.status_code == 201, r.text

with SessionLocal() as db:
    cross_family_leak = (
        db.query(models.AccountEmailEvent)
        .filter_by(to_email="emailparent@example.com", event_type="extension_request_approval")
        .count()
    )
    assert cross_family_leak == 1, "Family A's parent must not get emailed about Family B's request"
    print("No cross-family email leakage: OK")

print("\nALL SMOKE_EMAIL_APPROVAL CHECKS PASSED")
