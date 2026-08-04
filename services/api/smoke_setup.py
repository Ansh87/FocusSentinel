import sys, os, datetime
sys.path.insert(0, "../../packages/rules-engine")
sys.path.insert(0, "../../packages/activity-classifier")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.expanduser('~')}/smoke_setup.db"
os.environ["JWT_SECRET"] = "test-secret"

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

# --- parent A: walk through setup step by step ---
r = client.post("/auth/register", json={"email": "setupA@test.com", "password": "password123", "display_name": "A", "role": "parent"})
tokenA = r.json()["access_token"]
HA = {"Authorization": f"Bearer {tokenA}"}

r = client.post("/families", json={"name": "Saini Family", "timezone": "America/Chicago"}, headers=HA)
assert r.status_code == 201, r.text
family_id = r.json()["id"]

r = client.get(f"/families/{family_id}/setup-status", headers=HA)
assert r.status_code == 200, r.text
status = r.json()
assert status["family_profile_completed"] is True
assert status["student_added"] is False
assert status["first_rule_created"] is False
assert status["device_connected"] is False
assert status["is_complete"] is False
assert status["completed_steps"] == 1, status
assert status["started_at"] is not None
print("setup-status after family creation only: OK")

# editing the family name/timezone (PATCH)
r = client.patch(f"/families/{family_id}", json={"name": "Saini Family Updated", "timezone": "America/New_York"}, headers=HA)
assert r.status_code == 200 and r.json()["name"] == "Saini Family Updated", r.text
print("PATCH /families/{id}: OK")

# add a student -> student_added flips true
r = client.post("/students", json={"family_id": family_id, "display_name": "Ansh", "age_range": "13_15", "timezone": "UTC"}, headers=HA)
assert r.status_code == 201, r.text
student_id = r.json()["id"]

r = client.get(f"/families/{family_id}/setup-status", headers=HA)
status = r.json()
assert status["student_added"] is True
assert status["is_complete"] is False
assert status["completed_steps"] == 2, status
assert "Choose websites and create your first rule" in status["remaining_steps"]
print("setup-status after adding a student: OK")

# create a rule -> first_rule_created flips true, and family becomes complete
# (games category needs to exist first, same as smoke53.py)
from app.database import SessionLocal
from app import models
with SessionLocal() as _db:
    if not _db.query(models.ActivityCategory).filter_by(key="games").first():
        _db.add(models.ActivityCategory(key="games", label="Games"))
        _db.commit()

r = client.post("/rules", json={
    "student_id": student_id, "name": "Games limit", "scope_type": "category",
    "scope_category_key": "games", "warning_one_at_minutes": 20, "daily_limit_minutes": 30,
}, headers=HA)
assert r.status_code == 201, r.text

r = client.get(f"/families/{family_id}/setup-status", headers=HA)
status = r.json()
assert status["first_rule_created"] is True
assert status["is_complete"] is True, status  # device is optional, so complete now
assert status["completed_at"] is not None
assert status["remaining_steps"] == ["Connect a student device"], status
print("setup-status: is_complete becomes true once family+student+rule exist (device optional): OK")

# skip device connection explicitly
r = client.post(f"/families/{family_id}/setup-status/skip-device", headers=HA)
assert r.status_code == 200 and r.json()["device_connect_skipped"] is True, r.text
r = client.get(f"/families/{family_id}/setup-status", headers=HA)
assert r.json()["remaining_steps"] == [], r.json()
assert r.json()["completed_steps"] == 4, r.json()
print("skip-device: OK")

# dismiss reminder
r = client.post(f"/families/{family_id}/setup-status/dismiss-reminder", headers=HA)
assert r.status_code == 200 and r.json()["reminder_dismissed_until"] is not None, r.text
print("dismiss-reminder: OK")

# --- parent B: a second, unrelated account cannot see parent A's setup status or edit their family ---
r = client.post("/auth/register", json={"email": "setupB@test.com", "password": "password123", "display_name": "B", "role": "parent"})
tokenB = r.json()["access_token"]
HB = {"Authorization": f"Bearer {tokenB}"}

r = client.get(f"/families/{family_id}/setup-status", headers=HB)
assert r.status_code == 403, r.text
r = client.patch(f"/families/{family_id}", json={"name": "Hijacked"}, headers=HB)
assert r.status_code == 403, r.text
r = client.get(f"/families/{family_id}", headers=HB)
assert r.status_code == 403, r.text
print("cross-family isolation on family/setup-status endpoints: OK")

# --- fresh account with zero families never sees Alex/demo data ---
r = client.post("/students", json={"family_id": family_id, "display_name": "Alex", "age_range": "13_15", "timezone": "UTC"}, headers=HB)
assert r.status_code == 403, r.text  # B is not a member of A's family, can't add students to it either
print("parent B cannot add students to parent A's family: OK")

print("\nALL SMOKE_SETUP CHECKS PASSED")
