import sys, os
sys.path.insert(0, "../../packages/rules-engine")
sys.path.insert(0, "../../packages/activity-classifier")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.expanduser('~')}/smoke22b.db"
os.environ["JWT_SECRET"] = "test-secret"

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
r = client.post("/auth/register", json={"email":"p22b@test.com","password":"password123","display_name":"P","role":"parent"})
assert r.status_code == 201, r.text
token = r.json()["access_token"]
H = {"Authorization": f"Bearer {token}"}
r = client.post("/families", json={"name":"F","timezone":"UTC"}, headers=H)
family_id = r.json()["id"]
r = client.post("/students", json={"family_id": family_id, "display_name":"K", "age_range":"13_15", "timezone":"UTC"}, headers=H)
student_id = r.json()["id"]

r = client.get(f"/students/{student_id}/usage/today", headers=H)
assert r.status_code == 200, r.text
body = r.json()
assert "total_seconds_by_rule" in body, body
print("usage/today OK, total_seconds_by_rule:", body["total_seconds_by_rule"])
print("PASS")
