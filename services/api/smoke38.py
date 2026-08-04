import sys, os
sys.path.insert(0, "../../packages/rules-engine")
sys.path.insert(0, "../../packages/activity-classifier")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.expanduser('~')}/smoke38.db"
os.environ["JWT_SECRET"] = "test-secret"

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app import models
from app.security import create_password_reset_token

client = TestClient(app)

# --- setup: parent + family + two students ---
r = client.post("/auth/register", json={"email":"p38@test.com","password":"password123","display_name":"Parent","role":"parent"})
token = r.json()["access_token"]
H = {"Authorization": f"Bearer {token}"}
r = client.post("/families", json={"name":"Fam38","timezone":"UTC"}, headers=H)
family_id = r.json()["id"]
r = client.post("/students", json={"family_id": family_id, "display_name":"Kid A", "age_range":"13_15", "timezone":"UTC"}, headers=H)
student_a = r.json()["id"]
r = client.post("/students", json={"family_id": family_id, "display_name":"Kid B", "age_range":"13_15", "timezone":"UTC"}, headers=H)
student_b = r.json()["id"]

# --- student login lifecycle ---
r = client.get(f"/students/{student_a}/login", headers=H)
assert r.status_code == 200 and r.json() == {"has_login": False, "email": None}, r.json()

r = client.post(f"/students/{student_a}/login", json={"email":"kida@test.com","password":"kidpass123"}, headers=H)
assert r.status_code == 200, r.text
assert r.json() == {"has_login": True, "email": "kida@test.com"}, r.json()

r = client.get(f"/students/{student_a}/login", headers=H)
assert r.json() == {"has_login": True, "email": "kida@test.com"}, r.json()
print("student login create + status: OK")

# login as the student
r = client.post("/auth/login", json={"email":"kida@test.com","password":"kidpass123"})
assert r.status_code == 200, r.text
assert r.json()["role"] == "student", r.json()
SH = {"Authorization": f"Bearer {r.json()['access_token']}"}

r = client.get("/students/me", headers=SH)
assert r.status_code == 200 and r.json()["id"] == student_a, r.json()
print("student login + /students/me: OK")

# own-data access works
for path in [f"/students/{student_a}/usage/today", f"/rules/student/{student_a}", f"/device-health?student_id={student_a}"]:
    r = client.get(path, headers=SH)
    assert r.status_code == 200, (path, r.text)
print("student can read own usage/rules/device-health: OK")

# cross-student access is blocked
for path in [f"/students/{student_b}/usage/today", f"/rules/student/{student_b}", f"/device-health?student_id={student_b}"]:
    r = client.get(path, headers=SH)
    assert r.status_code == 403, (path, r.status_code, r.text)
print("student blocked from another student's data: OK")

# student can self-file an extension request, but not for another student
r = client.post("/extension-requests", json={"student_id": student_a, "reason_code": "friends", "requested_minutes": 15, "explanation": "test"}, headers=SH)
assert r.status_code == 201, r.text
r = client.post("/extension-requests", json={"student_id": student_b, "reason_code": "friends", "requested_minutes": 15}, headers=SH)
assert r.status_code == 403, r.text
print("student extension-request self-filing scoped correctly: OK")

# student still blocked from parent-only actions
r = client.post("/rules", json={"student_id": student_a, "name": "x", "scope_type":"category", "scope_category_key":"games", "daily_limit_minutes":10, "warning_one_at_minutes":8}, headers=SH)
assert r.status_code == 403, r.text
print("student blocked from creating rules: OK")

print("PART 1 (student accounts + scoping) PASSED")

# --- change-password (signed in) ---
r = client.post("/auth/change-password", json={"current_password":"password123","new_password":"newpassword456"}, headers=H)
assert r.status_code == 200, r.text
r = client.post("/auth/login", json={"email":"p38@test.com","password":"password123"})
assert r.status_code == 401, "old password should no longer work"
r = client.post("/auth/login", json={"email":"p38@test.com","password":"newpassword456"})
assert r.status_code == 200, r.text
print("change-password: OK")

r = client.post("/auth/change-password", json={"current_password":"wrong","new_password":"whatever12"}, headers=H)
assert r.status_code == 401, r.text
print("change-password rejects wrong current password: OK")

# --- forgot password flow ---
r = client.post("/auth/request-password-reset", json={"email":"p38@test.com"})
assert r.status_code == 200, r.text
r_unknown = client.post("/auth/request-password-reset", json={"email":"nobody@nowhere.com"})
assert r_unknown.status_code == 200 and r_unknown.json() == r.json(), "response shape must not leak whether the email exists"
print("request-password-reset: same generic response for known/unknown email: OK")

db = SessionLocal()
user = db.query(models.User).filter_by(email="p38@test.com").first()
ev = db.query(models.AccountEmailEvent).filter_by(event_type="password_reset").order_by(models.AccountEmailEvent.created_at.desc()).first()
assert ev is not None, "expected a queued password_reset account email"
assert ev.to_email == "p38@test.com", ev.to_email
assert ev.status == "queued", ev.status
print("password_reset account email queued correctly:", ev.payload)

token_for_reset = create_password_reset_token(user.id)
db.close()

r = client.post("/auth/reset-password", json={"token": token_for_reset, "new_password": "resetpassword789"})
assert r.status_code == 200, r.text
r = client.post("/auth/login", json={"email":"p38@test.com","password":"newpassword456"})
assert r.status_code == 401, "old password should no longer work after reset"
r = client.post("/auth/login", json={"email":"p38@test.com","password":"resetpassword789"})
assert r.status_code == 200, r.text
print("reset-password: OK")

r = client.post("/auth/reset-password", json={"token": "garbage.token.here", "new_password": "whatever12"})
assert r.status_code == 400, r.text
print("reset-password rejects invalid token: OK")

# --- usage/history ---
r = client.get(f"/students/{student_a}/usage/history?days=7", headers=H)
assert r.status_code == 200, r.text
body = r.json()
assert body["student_id"] == student_a
assert len(body["days"]) == 7, body
assert all("total_seconds_by_category" in d for d in body["days"]), body
print("usage/history shape OK:", body["days"][0])

print("PART 2 (password reset + history) PASSED")
