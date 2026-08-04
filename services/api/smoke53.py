import sys, os
sys.path.insert(0, "../../packages/rules-engine")
sys.path.insert(0, "../../packages/activity-classifier")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.expanduser('~')}/smoke53.db"
os.environ["JWT_SECRET"] = "test-secret"

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app import models

client = TestClient(app)

# Categories aren't seeded at startup in this build -- only created on demand
# by demo.py / websites.py -- so insert "games" directly rather than routing
# through /demo/load (which would attach an unrelated demo family/student to
# this same parent account and throw off the later "delete account only once
# every student is gone" assertions below).
with SessionLocal() as _db:
    if not _db.query(models.ActivityCategory).filter_by(key="games").first():
        _db.add(models.ActivityCategory(key="games", label="Games"))
        _db.commit()

# --- setup: parent + family + two students (eldest + younger) ---
r = client.post("/auth/register", json={"email": "p53@test.com", "password": "password123", "display_name": "Parent Fifty Three", "role": "parent"})
assert r.status_code == 201, r.text
token = r.json()["access_token"]
H = {"Authorization": f"Bearer {token}"}

r = client.get("/auth/me", headers=H)
assert r.status_code == 200, r.text
assert r.json()["display_name"] == "Parent Fifty Three", r.json()
print("GET /auth/me: OK")

r = client.post("/families", json={"name": "Fam53", "timezone": "UTC"}, headers=H)
family_id = r.json()["id"]

r = client.post("/students", json={"family_id": family_id, "display_name": "Eldest", "age_range": "16_17", "timezone": "UTC"}, headers=H)
eldest_id = r.json()["id"]
assert r.json()["is_sibling_manager"] is False, r.json()

r = client.post("/students", json={"family_id": family_id, "display_name": "Younger", "age_range": "8_12", "timezone": "UTC"}, headers=H)
younger_id = r.json()["id"]

# --- add a third student later ("add more students" ability) ---
r = client.post("/students", json={"family_id": family_id, "display_name": "Third", "age_range": "13_15", "timezone": "UTC"}, headers=H)
third_id = r.json()["id"]
r = client.get(f"/students/family/{family_id}", headers=H)
assert r.status_code == 200 and len(r.json()) == 3, r.json()
print("add extra student anytime: OK")

# --- sibling manager grant requires a login first ---
r = client.post(f"/students/{eldest_id}/sibling-manager", headers=H)
assert r.status_code == 400, r.text
print("sibling-manager grant blocked without login: OK")

r = client.post(f"/students/{eldest_id}/login", json={"email": "eldest53@test.com", "password": "eldestpass123"}, headers=H)
assert r.status_code == 200, r.text

r = client.post(f"/students/{eldest_id}/sibling-manager", headers=H)
assert r.status_code == 200 and r.json() == {"student_id": eldest_id, "is_sibling_manager": True}, r.json()
print("sibling-manager grant: OK")

r = client.get(f"/students/family/{family_id}", headers=H)
by_id = {s["id"]: s for s in r.json()}
assert by_id[eldest_id]["is_sibling_manager"] is True
assert by_id[younger_id]["is_sibling_manager"] is False
print("is_sibling_manager reflected in list_students: OK")

# --- eldest sibling logs in ---
r = client.post("/auth/login", json={"email": "eldest53@test.com", "password": "eldestpass123"})
assert r.status_code == 200, r.text
eldest_token = r.json()["access_token"]
EH = {"Authorization": f"Bearer {eldest_token}"}

r = client.get("/students/me", headers=EH)
assert r.status_code == 200 and r.json()["is_sibling_manager"] is True, r.json()
print("GET /students/me reflects sibling-manager flag: OK")

# eldest can read a younger sibling's data
r = client.get(f"/students/{younger_id}/usage/today", headers=EH)
assert r.status_code == 200, r.text
r = client.get(f"/rules/student/{younger_id}", headers=EH)
assert r.status_code == 200, r.text
print("sibling-manager read access to younger sibling: OK")

# eldest can create/edit a rule for the younger sibling
r = client.post("/rules", json={
    "student_id": younger_id, "name": "Games limit", "scope_type": "category",
    "scope_category_key": "games", "warning_one_at_minutes": 20, "daily_limit_minutes": 30,
}, headers=EH)
assert r.status_code == 201, r.text
rule_id = r.json()["id"]

r = client.put(f"/rules/{rule_id}", json={"daily_limit_minutes": 45}, headers=EH)
assert r.status_code == 200 and r.json()["daily_limit_minutes"] == 45, r.text
print("sibling-manager can create/edit a sibling's rule: OK")

# but eldest cannot manage a rule for THEMSELVES via the sibling-manager grant
r = client.post("/rules", json={
    "student_id": eldest_id, "name": "Self rule", "scope_type": "category",
    "scope_category_key": "games", "warning_one_at_minutes": 20, "daily_limit_minutes": 30,
}, headers=EH)
assert r.status_code == 403, r.text
print("sibling-manager blocked from managing self via grant: OK")

# and the THIRD student -- no grant needed check, still same family, should also be manageable
r = client.get(f"/students/{third_id}/usage/today", headers=EH)
assert r.status_code == 200, r.text

# a plain (non-manager) student cannot manage anyone
r = client.post(f"/students/{third_id}/login", json={"email": "third53@test.com", "password": "thirdpass123"}, headers=H)
assert r.status_code == 200, r.text
r = client.post("/auth/login", json={"email": "third53@test.com", "password": "thirdpass123"})
third_token = r.json()["access_token"]
TH = {"Authorization": f"Bearer {third_token}"}
r = client.get(f"/rules/student/{younger_id}", headers=TH)
assert r.status_code == 403, r.text
r = client.put(f"/rules/{rule_id}", json={"daily_limit_minutes": 10}, headers=TH)
assert r.status_code == 403, r.text
print("non-manager student blocked from siblings' data: OK")

# eldest approves an extension request for younger sibling
r = client.post("/extension-requests", json={"student_id": younger_id, "rule_id": rule_id, "requested_minutes": 10, "reason_code": "other"}, headers=EH)
assert r.status_code == 201, r.text
req_id = r.json()["id"]
r = client.post(f"/extension-requests/{req_id}/approve", json={"minutes": 10}, headers=EH)
assert r.status_code == 200 and r.json()["status"] == "approved", r.text
print("sibling-manager approve extension request: OK")

# revoke the grant, eldest loses management access again
r = client.delete(f"/students/{eldest_id}/sibling-manager", headers=H)
assert r.status_code == 200 and r.json()["is_sibling_manager"] is False, r.text
r = client.put(f"/rules/{rule_id}", json={"daily_limit_minutes": 20}, headers=EH)
assert r.status_code == 403, r.text
print("sibling-manager revoke: OK")

# --- clear activity history ---
r = client.post("/devices/register", json={"student_id": younger_id, "device_type": "browser_extension", "name": "dev"}, headers=H)
device_id = r.json()["device_id"]
device_token = r.json()["device_token"]
DH = {"Authorization": f"Bearer {device_token}"}
import datetime
now = datetime.datetime.utcnow()
r = client.post("/usage-events/batch", json={
    "device_id": device_id,
    "events": [{
        "identifier": "roblox.com", "category_key": "games",
        "started_at": (now - datetime.timedelta(minutes=5)).isoformat() + "Z",
        "ended_at": now.isoformat() + "Z", "active_duration_seconds": 300,
        "classification_source": "catalog", "idempotency_key": "smoke53-1",
    }],
}, headers=DH)
assert r.status_code == 200, r.text

r = client.get(f"/students/{younger_id}/usage/history?days=7", headers=H)
assert r.status_code == 200
total = sum(d["total_seconds"] for d in r.json()["days"])
assert total > 0, r.json()

r = client.delete(f"/students/{younger_id}/usage/history", headers=H)
assert r.status_code == 200 and r.json()["status"] == "history_cleared", r.text

r = client.get(f"/students/{younger_id}/usage/history?days=7", headers=H)
total = sum(d["total_seconds"] for d in r.json()["days"])
assert total == 0, r.json()
print("clear activity history: OK")

# --- delete a student, cascades everything ---
r = client.delete(f"/students/{third_id}", headers=H)
assert r.status_code == 200 and r.json()["status"] == "student_deleted", r.text
r = client.get(f"/students/family/{family_id}", headers=H)
assert len(r.json()) == 2, r.json()
# deleted student's login can no longer sign in
r = client.post("/auth/login", json={"email": "third53@test.com", "password": "thirdpass123"})
assert r.status_code == 401, r.text
print("delete student cascade: OK")

# --- delete parent account is blocked while students remain ---
r = client.delete("/auth/account", headers=H)
assert r.status_code == 409, r.text
print("delete account blocked with remaining students: OK")

# remove the remaining two students, then delete succeeds
client.delete(f"/students/{eldest_id}", headers=H)
client.delete(f"/students/{younger_id}", headers=H)
r = client.delete("/auth/account", headers=H)
assert r.status_code == 200 and r.json()["status"] == "account_deleted", r.text
print("delete account after all students removed: OK")

r = client.post("/auth/login", json={"email": "p53@test.com", "password": "password123"})
assert r.status_code == 401, r.text
print("deleted parent account can no longer sign in: OK")

# --- demo account is protected from deletion ---
# (fresh test DB has no pre-registered demo user -- production seeds this via
# database/seed/seed.py; register it here just for this assertion)
r = client.post("/auth/register", json={"email": "parent@focussentinel.demo", "password": "demo-password-123", "display_name": "Demo Parent", "role": "parent"})
assert r.status_code == 201, r.text
r = client.post("/auth/login", json={"email": "parent@focussentinel.demo", "password": "demo-password-123"})
demo_token = r.json()["access_token"]
DMH = {"Authorization": f"Bearer {demo_token}"}
r = client.delete("/auth/account", headers=DMH)
assert r.status_code == 400, r.text
print("demo account deletion blocked: OK")

print("\nALL SMOKE53 CHECKS PASSED")
