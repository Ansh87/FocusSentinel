import sys, os
sys.path.insert(0, "../../packages/rules-engine")
sys.path.insert(0, "../../packages/activity-classifier")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.expanduser('~')}/smoke_missing_table.db"
os.environ["JWT_SECRET"] = "test-secret"

from fastapi.testclient import TestClient
from app.main import app
from app.database import engine
from app import models

client = TestClient(app)

# Simulate exactly the production symptom: the sibling_manager_grants table
# doesn't exist (e.g. this deployment hasn't run create_all against it, or
# it got dropped) while everything else is normal.
models.SiblingManagerGrant.__table__.drop(bind=engine)

r = client.post("/auth/register", json={"email": "missing@test.com", "password": "password123", "display_name": "P", "role": "parent"})
token = r.json()["access_token"]
H = {"Authorization": f"Bearer {token}"}
r = client.post("/families", json={"name": "F", "timezone": "UTC"}, headers=H)
family_id = r.json()["id"]
r = client.post("/students", json={"family_id": family_id, "display_name": "Kid", "age_range": "13_15", "timezone": "UTC"}, headers=H)
assert r.status_code == 201, r.text

# This is the exact call that 500'd in production (GET /students/family/{id})
r = client.get(f"/students/family/{family_id}", headers=H)
assert r.status_code == 200, r.text
assert r.json()[0]["is_sibling_manager"] is False, r.json()
print("list_students survives a missing sibling_manager_grants table: OK")

# and the session isn't left in an aborted state for subsequent queries
r = client.get(f"/students/family/{family_id}", headers=H)
assert r.status_code == 200, r.text
print("session usable for follow-up requests after the guarded failure: OK")
