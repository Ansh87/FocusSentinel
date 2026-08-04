import sys, os
sys.path.insert(0, "../../packages/rules-engine")
sys.path.insert(0, "../../packages/activity-classifier")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.expanduser('~')}/smoke22.db"
os.environ["JWT_SECRET"] = "test-secret"

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app import models

client = TestClient(app)

# register + login
r = client.post("/auth/register", json={"email":"p22@test.com","password":"password123","display_name":"P22","role":"parent"})
assert r.status_code == 201, r.text
token = r.json()["access_token"]
H = {"Authorization": f"Bearer {token}"}

r = client.post("/families", json={"name":"Fam22","timezone":"America/Chicago"}, headers=H)
assert r.status_code == 201, r.text
family_id = r.json()["id"]

r = client.post("/students", json={"family_id": family_id, "display_name":"Kid", "age_range":"13_15", "timezone":"America/Chicago"}, headers=H)
assert r.status_code == 201, r.text
student_id = r.json()["id"]

r = client.post("/devices/register", json={"student_id": student_id, "device_type":"browser_extension", "name":"ext", "platform_identifier": None}, headers=H)
assert r.status_code == 201, r.text
device_id = r.json()["device_id"]
device_token = r.json()["device_token"]
DH = {"Authorization": f"Bearer {device_token}"}

# catalog fetch (auto-seed)
r = client.get(f"/websites/catalog?family_id={family_id}", headers=H)
assert r.status_code == 200, r.text
catalog = r.json()
labels = {w["label"]: w for w in catalog}
assert "TikTok" in labels
assert "YouTube Shorts" in labels
assert "YouTube" in labels
assert "Instagram Reels" in labels
print("catalog rows:", len(catalog))

tiktok = labels["TikTok"]
yt_shorts = labels["YouTube Shorts"]
yt = labels["YouTube"]
ig_reels = labels["Instagram Reels"]

# add a custom website
r = client.post("/websites", json={"family_id": family_id, "domain": "https://www.KhanAcademy.org/videos", "label": "Khan Academy Videos", "category_key": "educational"}, headers=H)
assert r.status_code == 201, r.text
khan = r.json()
assert khan["domain"] == "khanacademy.org", khan
print("custom website normalized domain:", khan["domain"])

# duplicate add returns same row (idempotent)
r2 = client.post("/websites", json={"family_id": family_id, "domain": "khanacademy.org", "label": "dup", "category_key": "educational"}, headers=H)
assert r2.status_code == 201
assert r2.json()["id"] == khan["id"], "expected idempotent dedupe"

# invalid domain rejected
r3 = client.post("/websites", json={"family_id": family_id, "domain": "not a domain!!", "label": "bad"}, headers=H)
assert r3.status_code == 400, r3.text
print("invalid domain rejected ok")

# create a multi-website rule: TikTok + YouTube Shorts + Instagram Reels, 10 minute combined limit
r = client.post("/rules", json={
    "student_id": student_id,
    "name": "Short-form combined",
    "scope_type": "website",
    "website_ids": [tiktok["id"], yt_shorts["id"], ig_reels["id"]],
    "daily_limit_minutes": 15,
    "warning_one_at_minutes": 8,
    "warning_two_after_additional_minutes": 3,
    "block_after_warning_two_seconds": 30,
}, headers=H)
assert r.status_code == 201, r.text
rule = r.json()
assert len(rule["websites"]) == 3, rule
print("rule created with websites:", [w["label"] for w in rule["websites"]])
rule_id = rule["id"]

def post_event(identifier, seconds, idem):
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    return client.post("/usage-events/batch", json={
        "device_id": device_id,
        "events": [{
            "identifier": identifier,
            "started_at": (now - timedelta(seconds=seconds)).isoformat(),
            "ended_at": now.isoformat(),
            "active_duration_seconds": seconds,
            "classification_source": "catalog",
            "idempotency_key": idem,
        }]
    }, headers=DH)

# 4 minutes on tiktok.com
r = post_event("tiktok.com", 240, "e1")
assert r.status_code == 200, r.text
ev = r.json()["evaluations"][0]
print("after 4min tiktok:", ev["minutes_used"], ev["level"])
assert ev["level"] == "none"

# 3 minutes on youtube.com/shorts -> combined 7 min, still under 8 warning
r = post_event("youtube.com/shorts", 180, "e2")
assert r.status_code == 200, r.text
ev = r.json()["evaluations"][0]
print("after +3min yt-shorts (combined 7min):", ev["minutes_used"], ev["level"])
assert abs(ev["minutes_used"] - 7.0) < 0.05, ev
# 7 min is >= 80% of the 8-min warning_one threshold, so the engine's
# informational progress_notice level is expected here, not "none".
assert ev["level"] == "progress_notice", ev

# path-specific matching sanity: plain youtube.com (not /shorts) should NOT count toward this rule
r = post_event("youtube.com", 600, "e3")
assert r.status_code == 200, r.text
ev = r.json()["evaluations"][0]
print("youtube.com (not shorts) level:", ev["level"], "limit:", ev["limit_minutes"])
assert ev["limit_minutes"] is None, "plain youtube.com should not match the short-form rule"

# 2 more minutes on instagram.com/reels -> combined 9 min, crosses warning_one at 8
r = post_event("instagram.com/reels", 120, "e4")
assert r.status_code == 200, r.text
ev = r.json()["evaluations"][0]
print("after +2min ig-reels (combined 9min):", ev["minutes_used"], ev["level"])
assert abs(ev["minutes_used"] - 9.0) < 0.05, ev
assert ev["level"] == "warning_one", ev

db = SessionLocal()
totals = db.query(models.DailyUsageTotal).filter_by(student_id=student_id).all()
for t in totals:
    w = db.get(models.Website, t.website_id) if t.website_id else None
    print("DailyUsageTotal:", w.domain if w else None, (w.url_pattern if w else None), t.total_seconds)
db.close()

# most-specific-match priority: instagram.com (bare) should classify as social_media (Instagram catalog), not reels
r = post_event("instagram.com", 60, "e5")
assert r.status_code == 200, r.text
ev = r.json()["evaluations"][0]
print("instagram.com (bare) level:", ev["level"], "limit:", ev["limit_minutes"])
assert ev["limit_minutes"] is None, "bare instagram.com should not match the reels-only rule"

# update rule's website_ids -> drop instagram reels, add facebook.com/reel
labels2 = labels
fb_reels = labels2["Facebook Reels"]
r = client.put(f"/rules/{rule_id}", json={"website_ids": [tiktok["id"], yt_shorts["id"], fb_reels["id"]]}, headers=H)
assert r.status_code == 200, r.text
updated = r.json()
assert sorted(w["label"] for w in updated["websites"]) == sorted(["TikTok", "YouTube Shorts", "Facebook Reels"]), updated
print("rule updated websites:", [w["label"] for w in updated["websites"]])

print("ALL SMOKE TESTS PASSED")

# --- backward compatibility: legacy category-scoped rule still works ---
r = client.post("/websites", json={"family_id": family_id, "domain": "roblox.com", "label": "Roblox", "category_key": "games"}, headers=H)
assert r.status_code == 201, r.text

r = client.post("/rules", json={
    "student_id": student_id,
    "name": "Games category limit",
    "scope_type": "category",
    "scope_category_key": "games",
    "daily_limit_minutes": 5,
    "warning_one_at_minutes": 4,
    "warning_two_after_additional_minutes": 1,
    "block_after_warning_two_seconds": 30,
}, headers=H)
assert r.status_code == 201, r.text
cat_rule = r.json()
assert cat_rule["scope_category_key"] == "games", cat_rule
assert cat_rule["websites"] == [], cat_rule
print("category rule created:", cat_rule["name"], cat_rule["scope_category_key"])

r = post_event("roblox.com", 300, "cat1")
assert r.status_code == 200, r.text
ev = r.json()["evaluations"][0]
print("after 5min roblox (category rule):", ev["minutes_used"], ev["level"])
# warning_one_at_minutes=4, warning_two_after_additional_minutes=1 => the
# warning_two threshold is exactly 5, so 5 min used lands on warning_two.
assert ev["level"] == "warning_two", ev

print("BACKWARD-COMPAT CHECK PASSED")
