import sys, os
sys.path.insert(0, "../../packages/rules-engine")
sys.path.insert(0, "../../packages/activity-classifier")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.expanduser('~')}/smokefinal.db"
os.environ["JWT_SECRET"] = "test-secret"

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

# fresh personal account -> onboarding flow
r = client.post("/auth/register", json={"email":"newparent@test.com","password":"password123","display_name":"New Parent","role":"parent"})
assert r.status_code == 201, r.text
token = r.json()["access_token"]
H = {"Authorization": f"Bearer {token}"}

r = client.get("/families/mine", headers=H)
assert r.json() == [], "brand new account should have zero families"

r = client.post("/families", json={"name": "My Family", "timezone": "UTC"}, headers=H)
assert r.status_code == 201, r.text
family_id = r.json()["id"]
r = client.post("/students", json={"family_id": family_id, "display_name": "Sam", "age_range": "8_12", "timezone": "UTC"}, headers=H)
assert r.status_code == 201, r.text
student_id = r.json()["id"]

# multi-website rule via the new modal-style payload (category + website variants)
r = client.get(f"/websites/catalog?family_id={family_id}", headers=H)
catalog = {w["label"]: w for w in r.json()}
r = client.post("/rules", json={
    "student_id": student_id, "name": "Short-form video limit", "scope_type": "website",
    "website_ids": [catalog["TikTok"]["id"], catalog["YouTube Shorts"]["id"]],
    "daily_limit_minutes": 30, "warning_one_at_minutes": 24,
    "warning_two_after_additional_minutes": 3, "block_after_warning_two_seconds": 60,
    "days_of_week": [0,1,2,3,4,5,6], "reset_time": "00:00",
}, headers=H)
assert r.status_code == 201, r.text
rule = r.json()
assert sorted(w["label"] for w in rule["websites"]) == ["TikTok", "YouTube Shorts"], rule
print("onboarding + multi-website rule creation: OK")

# edit via PUT with student_id/scope_category_key (as the new Edit modal would)
r = client.put(f"/rules/{rule['id']}", json={"scope_category_key": "short_form_video", "daily_limit_minutes": 45}, headers=H)
assert r.status_code == 200, r.text
assert r.json()["websites"] == [] and r.json()["scope_category_key"] == "short_form_video", r.json()
print("rule edit scope switch via modal payload: OK")

# pause / resume
r = client.put(f"/rules/{rule['id']}", json={"active": False}, headers=H)
assert r.json()["active"] is False
r = client.put(f"/rules/{rule['id']}", json={"active": True}, headers=H)
assert r.json()["active"] is True
print("pause/resume: OK")

# delete
r = client.delete(f"/rules/{rule['id']}", headers=H)
assert r.status_code == 204
print("delete: OK")

# usage/today shape sanity for a student with no usage yet
r = client.get(f"/students/{student_id}/usage/today", headers=H)
assert r.status_code == 200 and r.json()["total_seconds_by_rule"] == {}, r.json()
print("usage/today OK for empty student")

print("FINAL REGRESSION PASSED")
