import sys, os
sys.path.insert(0, "../../packages/rules-engine")
sys.path.insert(0, "../../packages/activity-classifier")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.expanduser('~')}/smoke_demo_isolation.db"
os.environ["JWT_SECRET"] = "test-secret"

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

# A real (non-reserved-email) parent must never be able to inject demo data
# into their own account via /demo/load, /demo/reset, or /demo/simulate --
# those are for the one reserved public demo login only.
r = client.post("/auth/register", json={"email": "realparent@test.com", "password": "password123", "display_name": "Real Parent", "role": "parent"})
token = r.json()["access_token"]
H = {"Authorization": f"Bearer {token}"}

r = client.post("/demo/load", headers=H)
assert r.status_code == 403, r.text
r = client.post("/demo/reset", headers=H)
assert r.status_code == 403, r.text
r = client.post("/demo/simulate", headers=H)
assert r.status_code == 403, r.text
print("non-demo account blocked from /demo/load, /demo/reset, /demo/simulate: OK")

# their family list is untouched (still empty -- no demo family got created)
r = client.get("/families/mine", headers=H)
assert r.status_code == 200 and r.json() == [], r.json()
print("no demo family created as a side effect of the blocked calls: OK")

# the reserved demo account is unaffected and still works exactly as before
r = client.post("/auth/register", json={"email": "parent@focussentinel.demo", "password": "demo-password-123", "display_name": "Demo Parent", "role": "parent"})
assert r.status_code == 201, r.text
r = client.post("/auth/login", json={"email": "parent@focussentinel.demo", "password": "demo-password-123"})
demo_token = r.json()["access_token"]
DH = {"Authorization": f"Bearer {demo_token}"}

r = client.post("/demo/load", headers=DH)
assert r.status_code == 200, r.text
r = client.post("/demo/simulate", headers=DH)
assert r.status_code == 200, r.text
r = client.post("/demo/reset", headers=DH)
assert r.status_code == 200, r.text
print("reserved demo account still has full access to all three endpoints: OK")

print("\nALL SMOKE_DEMO_ISOLATION CHECKS PASSED")
