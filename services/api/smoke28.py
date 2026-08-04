import sys, os
sys.path.insert(0, "../../packages/rules-engine")
sys.path.insert(0, "../../packages/activity-classifier")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.expanduser('~')}/smoke28.db"
os.environ["JWT_SECRET"] = "test-secret"

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app import models

client = TestClient(app)

# --- 1. demo self-heal on login ---
# simulate the "old thin seed family" scenario: register the reserved demo
# email manually (bypassing seed.py) with a differently-named family, then
# confirm login cleans it up and creates the rich demo family.
r = client.post("/auth/register", json={"email":"parent@focussentinel.demo","password":"demo-password-123","display_name":"Demo Parent","role":"parent"})
assert r.status_code == 201, r.text
token = r.json()["access_token"]
H = {"Authorization": f"Bearer {token}"}

# create an old-style thin family for this account (simulating old seed.py state)
r = client.post("/families", json={"name":"Demo Family","timezone":"America/Chicago"}, headers=H)
assert r.status_code == 201, r.text
thin_family_id = r.json()["id"]
r = client.post("/students", json={"family_id": thin_family_id, "display_name":"Demo Student", "age_range":"13_15", "timezone":"America/Chicago"}, headers=H)
assert r.status_code == 201, r.text

# now log in again (fresh call) -- should self-heal
r = client.post("/auth/login", json={"email":"parent@focussentinel.demo","password":"demo-password-123"})
assert r.status_code == 200, r.text
token2 = r.json()["access_token"]
H2 = {"Authorization": f"Bearer {token2}"}

r = client.get("/families/mine", headers=H2)
assert r.status_code == 200, r.text
fams = r.json()
print("families after self-heal login:", [f["name"] for f in fams])
assert len(fams) == 1, fams
assert fams[0]["name"] == "Demo Family (Sample Data)", fams

family_id = fams[0]["id"]
r = client.get(f"/students/family/{family_id}", headers=H2)
students = r.json()
assert len(students) == 1 and students[0]["display_name"] == "Alex", students
student_id = students[0]["id"]

r = client.get(f"/rules/student/{student_id}", headers=H2)
rules = r.json()
rule_names = sorted(r["name"] for r in rules)
print("rules after self-heal:", rule_names)
assert rule_names == ["Gaming limit", "Short-form video limit"], rule_names

r = client.get(f"/extension-requests?student_id={student_id}&status=pending", headers=H2)
assert len(r.json()) == 1, r.json()
print("pending extension request present: OK")

# login again -- must be idempotent, still exactly one family
r = client.post("/auth/login", json={"email":"parent@focussentinel.demo","password":"demo-password-123"})
token3 = r.json()["access_token"]
H3 = {"Authorization": f"Bearer {token3}"}
r = client.get("/families/mine", headers=H3)
assert len(r.json()) == 1, r.json()
print("idempotent re-login: OK")

print("PART 1 (demo self-heal) PASSED")

# --- 2. isolation check: a second, unrelated demo login gets its own copy ---
r = client.post("/auth/register", json={"email":"other@test.com","password":"password123","display_name":"Other","role":"parent"})
other_token = r.json()["access_token"]
OH = {"Authorization": f"Bearer {other_token}"}
r = client.post("/families", json={"name":"Not Demo","timezone":"UTC"}, headers=OH)
r = client.get("/families/mine", headers=OH)
assert [f["name"] for f in r.json()] == ["Not Demo"], r.json()
print("unrelated account untouched by demo self-heal: OK")

# reset demo (student_id/family_id from part 1)
r = client.post("/demo/reset", headers=H3)
assert r.status_code == 200, r.text
r = client.get("/families/mine", headers=OH)
assert [f["name"] for f in r.json()] == ["Not Demo"], "reset demo leaked into another account!"
print("Reset Demo isolated to the demo account only: OK")

# --- 3. rule update: reassign student + switch scope + delete ---
# Reset Demo above recreated the demo family under a fresh id -- refetch it
# rather than reusing the pre-reset family_id/student_id, which now point at
# deleted rows.
r = client.get("/families/mine", headers=H3)
family_id = r.json()[0]["id"]
r = client.get(f"/students/family/{family_id}", headers=H3)
student_id = [s for s in r.json() if s["display_name"] == "Alex"][0]["id"]

r = client.post("/students", json={"family_id": family_id, "display_name":"Jamie", "age_range":"8_12", "timezone":"America/Chicago"}, headers=H3)
jamie_id = r.json()["id"]

r = client.get(f"/rules/student/{student_id}", headers=H3)
video_rule = [x for x in r.json() if x["name"] == "Short-form video limit"][0]

# reassign to Jamie
r = client.put(f"/rules/{video_rule['id']}", json={"student_id": jamie_id}, headers=H3)
assert r.status_code == 200, r.text
assert r.json()["student_id"] == jamie_id, r.json()

# switch scope from category to explicit websites
r = client.get(f"/websites/catalog?family_id={family_id}", headers=H3)
catalog = {w["label"]: w for w in r.json()}
r = client.put(f"/rules/{video_rule['id']}", json={"website_ids": [catalog["TikTok"]["id"]]}, headers=H3)
assert r.status_code == 200, r.text
updated = r.json()
assert updated["scope_category_key"] is None, updated
assert [w["label"] for w in updated["websites"]] == ["TikTok"], updated
print("rule reassignment + scope switch: OK")

# delete it
r = client.delete(f"/rules/{video_rule['id']}", headers=H3)
assert r.status_code == 204, r.text
r = client.get(f"/rules/student/{jamie_id}", headers=H3)
assert all(x["id"] != video_rule["id"] for x in r.json())
print("rule delete: OK")

# --- 4. extension grant (Allow more time) ---
r = client.get(f"/rules/student/{student_id}", headers=H3)
game_rule = [x for x in r.json() if x["name"] == "Gaming limit"][0]
r = client.post("/extension-requests/grant", json={"student_id": student_id, "rule_id": game_rule["id"], "minutes": 20}, headers=H3)
assert r.status_code == 200, r.text
grant = r.json()
assert grant["status"] == "approved" and grant["requested_minutes"] == 20, grant
print("extension grant: OK")

print("PART 2 PASSED")

# --- 5. restriction wording (12-hour, "access is restricted") ---
# Reset first -- the extension grant above added 20 minutes to this same
# Gaming limit rule's effective threshold, which would otherwise make the
# simulate checkpoints undershoot restricted purely as a test-ordering
# artifact, not an app bug.
r = client.post("/demo/reset", headers=H3)
assert r.status_code == 200, r.text
r = client.get("/families/mine", headers=H3)
family_id = r.json()[0]["id"]
r = client.post("/demo/simulate", headers=H3)
assert r.status_code == 200, r.text
steps = r.json()["steps"]
restricted_steps = [s for s in steps if s["level"] == "restricted"]
assert restricted_steps, steps
msg = restricted_steps[0]["message"]
print("restricted message:", msg)
assert "access is restricted for today" in msg, msg
assert "Access resumes at 12:00 AM" in msg, msg
assert "00:00:00" not in msg, msg

# --- 6. device health statuses ---
r = client.get(f"/students/family/{family_id}", headers=H3)
alex_id = [s for s in r.json() if s["display_name"] == "Alex"][0]["id"]
r = client.get(f"/device-health?student_id={alex_id}", headers=H3)
assert r.status_code == 200, r.text
health = r.json()
print("device health:", health)
assert health[0]["platform_identifier"] == "Chrome", health
assert health[0]["status"] in ("connected", "delayed", "offline", "permission_issue", "revoked"), health

print("PART 3 PASSED")
