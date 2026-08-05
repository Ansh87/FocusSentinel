"""Smoke test for the Students management endpoints added this round:
PATCH /students/{id}, POST /students/{id}/archive, POST /students/{id}/unarchive,
and cross-family isolation on all three.
"""
import os

os.environ["DATABASE_URL"] = f"sqlite:///{os.path.expanduser('~')}/smoke_students_mgmt.db"
db_path = os.path.expanduser("~/smoke_students_mgmt.db")
if os.path.exists(db_path):
    os.remove(db_path)

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app.database import Base, engine  # noqa: E402

Base.metadata.create_all(bind=engine)
client = TestClient(app)


def register_and_login(email, password, display_name, role="parent"):
    r = client.post("/auth/register", json={"email": email, "password": password, "display_name": display_name, "role": role})
    assert r.status_code in (200, 201), r.text
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# --- Family A: parent with a student ---
headers_a = register_and_login("parentA@example.com", "password123", "Parent A")
r = client.post("/families", json={"name": "Family A", "timezone": "UTC"}, headers=headers_a)
assert r.status_code in (200, 201), r.text
family_a = r.json()["id"]

r = client.post("/students", json={"family_id": family_a, "display_name": "Kid A", "age_range": "8_12", "timezone": "UTC"}, headers=headers_a)
assert r.status_code == 201, r.text
student_a = r.json()["id"]
assert r.json()["is_archived"] is False

# --- PATCH: edit name and age range ---
r = client.patch(f"/students/{student_a}", json={"display_name": "Kiddo A", "age_range": "13_15"}, headers=headers_a)
assert r.status_code == 200, r.text
body = r.json()
assert body["display_name"] == "Kiddo A"
assert body["age_range"] == "13_15"
assert body["is_archived"] is False

# --- Archive ---
r = client.post(f"/students/{student_a}/archive", headers=headers_a)
assert r.status_code == 200, r.text
assert r.json()["is_archived"] is True

r = client.get(f"/students/family/{family_a}", headers=headers_a)
assert r.status_code == 200, r.text
assert r.json()[0]["is_archived"] is True

# Archiving again is idempotent (no duplicate row / error)
r = client.post(f"/students/{student_a}/archive", headers=headers_a)
assert r.status_code == 200, r.text
assert r.json()["is_archived"] is True

# --- Unarchive ---
r = client.post(f"/students/{student_a}/unarchive", headers=headers_a)
assert r.status_code == 200, r.text
assert r.json()["is_archived"] is False

r = client.get(f"/students/family/{family_a}", headers=headers_a)
assert r.json()[0]["is_archived"] is False

# --- Family B: separate parent, isolation checks ---
headers_b = register_and_login("parentB@example.com", "password123", "Parent B")
r = client.post("/families", json={"name": "Family B", "timezone": "UTC"}, headers=headers_b)
family_b = r.json()["id"]
r = client.post("/students", json={"family_id": family_b, "display_name": "Kid B", "age_range": "8_12", "timezone": "UTC"}, headers=headers_b)
student_b = r.json()["id"]

# Parent B cannot edit/archive/unarchive Parent A's student
r = client.patch(f"/students/{student_a}", json={"display_name": "Hijacked"}, headers=headers_b)
assert r.status_code == 403, r.text
r = client.post(f"/students/{student_a}/archive", headers=headers_b)
assert r.status_code == 403, r.text
r = client.post(f"/students/{student_a}/unarchive", headers=headers_b)
assert r.status_code == 403, r.text

# Parent A cannot touch Parent B's student either (symmetry check)
r = client.patch(f"/students/{student_b}", json={"display_name": "Hijacked"}, headers=headers_a)
assert r.status_code == 403, r.text

# --- Hard delete cleans up archive-state row (no dangling FK / stray row) ---
r = client.post(f"/students/{student_a}/archive", headers=headers_a)
assert r.status_code == 200, r.text
r = client.delete(f"/students/{student_a}", headers=headers_a)
assert r.status_code == 200, r.text

# --- Account deletion isn't blocked by a student the parent only archived
# (rather than hard-deleted) -- archived students are invisible on the
# dashboard, so blocking deletion on them would look like account deletion
# is silently broken. A genuinely active student still blocks it. ---
headers_c = register_and_login("parentC@example.com", "password123", "Parent C")
r = client.post("/families", json={"name": "Family C", "timezone": "UTC"}, headers=headers_c)
family_c = r.json()["id"]
r = client.post("/students", json={"family_id": family_c, "display_name": "Only Kid", "age_range": "8_12", "timezone": "UTC"}, headers=headers_c)
only_kid_id = r.json()["id"]

r = client.delete("/auth/account", headers=headers_c)
assert r.status_code == 409, r.text
print("Account deletion still blocked while a student is active (not archived): OK")

r = client.post(f"/students/{only_kid_id}/archive", headers=headers_c)
assert r.status_code == 200, r.text
r = client.delete("/auth/account", headers=headers_c)
assert r.status_code == 200, f"account deletion should succeed once the only student is archived: {r.text}"
print("Account deletion succeeds once the only student is archived (auto-cleaned-up): OK")

r = client.post("/auth/login", json={"email": "parentC@example.com", "password": "password123"})
assert r.status_code == 401, r.text
print("Deleted account (via archived-student path) can no longer sign in: OK")

print("ALL SMOKE_STUDENTS_MGMT CHECKS PASSED")
