"""Reproduces production-like foreign-key enforcement, which our normal
smoke tests never exercise -- database.py never issues `PRAGMA
foreign_keys=ON`, so SQLite silently ignores FK violations that Postgres
(the real production database) would reject with a 500. This script turns
FK enforcement on to catch exactly that class of bug before it ships.
"""
import os

os.environ["DATABASE_URL"] = f"sqlite:///{os.path.expanduser('~')}/smoke_fk_enforced.db"
db_path = os.path.expanduser("~/smoke_fk_enforced.db")
if os.path.exists(db_path):
    os.remove(db_path)

from sqlalchemy import event  # noqa: E402
from app.database import Base, engine  # noqa: E402

# Must be registered before ANY connection is opened (including the one
# create_all is about to make) -- SQLite's foreign_keys pragma is
# per-connection, and if this listener is attached after the pool's first
# connection is already established, it silently never applies, which is
# exactly the kind of false-negative this script exists to avoid.
@event.listens_for(engine, "connect")
def _enable_fk(dbapi_connection, connection_record):
    dbapi_connection.execute("PRAGMA foreign_keys=ON")


from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app import models  # noqa: E402

Base.metadata.create_all(bind=engine)

with engine.connect() as _c:
    fk_status = _c.exec_driver_sql("PRAGMA foreign_keys").scalar()
    print(f"PRAGMA foreign_keys = {fk_status} (must be 1 for this test to mean anything)")

client = TestClient(app)


def register_and_login(email, password, display_name, role="parent"):
    r = client.post("/auth/register", json={"email": email, "password": password, "display_name": display_name, "role": role})
    assert r.status_code in (200, 201), r.text
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


headers = register_and_login("fkparent@example.com", "password123", "FK Parent")
r = client.post("/families", json={"name": "FK Family", "timezone": "UTC"}, headers=headers)
assert r.status_code in (200, 201), r.text
family_id = r.json()["id"]

r = client.post("/students", json={"family_id": family_id, "display_name": "Kid", "age_range": "8_12", "timezone": "UTC"}, headers=headers)
assert r.status_code == 201, r.text
student_id = r.json()["id"]

# Custom website added to the family catalog (exactly what the "Add domain"
# button in the rule form does) -- this is the row that has no cleanup path
# in cascade.delete_family().
r = client.post("/websites", json={"family_id": family_id, "domain": "example.com", "label": "Example", "category_key": "other"}, headers=headers)
assert r.status_code in (200, 201), r.text
website_id = r.json()["id"]

r = client.post(
    "/rules",
    json={
        "student_id": student_id,
        "name": "Website limit",
        "scope_type": "website",
        "website_ids": [website_id],
        "daily_limit_minutes": 30,
        "warning_one_at_minutes": 24,
    },
    headers=headers,
)
assert r.status_code in (200, 201), r.text
rule_id = r.json()["id"]

r = client.post("/devices/register", json={"student_id": student_id, "device_type": "browser_extension", "name": "Test device"}, headers=headers)
assert r.status_code in (200, 201), r.text

r = client.post(
    "/notification-recipients",
    json={"family_id": family_id, "name": "Grandma", "relationship": "grandparent", "email": "g@example.com"},
    headers=headers,
)
assert r.status_code in (200, 201), r.text

print("Fixture built: family, student, custom website, website-scoped rule, device, notification recipient.")

# --- Attempt to delete just the student (cascade.delete_students path) ---
r = client.delete(f"/students/{student_id}", headers=headers)
print(f"DELETE /students/{{id}}: {r.status_code} {r.text if r.status_code >= 400 else 'OK'}")

# --- Attempt to delete the whole family directly through cascade.delete_family,
# exactly what /demo/reset does -- the custom website above is still attached
# to this family and was never touched by the student delete above.
from app.database import SessionLocal  # noqa: E402
from app import cascade  # noqa: E402

with SessionLocal() as db:
    try:
        cascade.delete_family(db, family_id)
        print("cascade.delete_family: OK")
    except Exception as e:
        print(f"cascade.delete_family: FAILED -- {type(e).__name__}: {e}")

# --- End-to-end: the exact real-world sequence that was reported broken --
# sign in as the reserved demo account, load demo data, add a custom
# website to it (as testing the multi-website rule feature would), run a
# simulation (usage -> warnings -> restriction -> extension request), then
# reset. Every step goes through the real HTTP endpoints, not internal
# helpers, and FK enforcement is still on.
demo_headers = register_and_login("parent@focussentinel.demo", "demopass123", "Demo Parent")

r = client.post("/demo/load", headers=demo_headers)
assert r.status_code == 200, r.text
demo_family_id = r.json()["family_id"]

r = client.post(
    "/websites",
    json={"family_id": demo_family_id, "domain": "customsite.com", "label": "Custom Site", "category_key": "other"},
    headers=demo_headers,
)
assert r.status_code in (200, 201), f"add custom website to demo family: {r.text}"
custom_site_id = r.json()["id"]

r = client.get(f"/students/family/{demo_family_id}", headers=demo_headers)
assert r.status_code == 200, r.text
demo_student_id = r.json()[0]["id"]

r = client.post(
    "/rules",
    json={
        "student_id": demo_student_id,
        "name": "Custom site limit",
        "scope_type": "website",
        "website_ids": [custom_site_id],
        "daily_limit_minutes": 20,
        "warning_one_at_minutes": 16,
    },
    headers=demo_headers,
)
assert r.status_code in (200, 201), f"create custom-website rule on demo family: {r.text}"

r = client.post("/demo/simulate", headers=demo_headers)
print(f"POST /demo/simulate (with custom website present): {r.status_code} {'OK' if r.status_code == 200 else r.text}")

r = client.post("/demo/reset", headers=demo_headers)
print(f"POST /demo/reset (with custom website present): {r.status_code} {'OK' if r.status_code == 200 else r.text}")

# --- Backend self-heal: a real (non-demo) account whose family got stuck
# with the demo marker name by the old bug should get it renamed the next
# time it lists its families. ---
healed_headers = register_and_login("healme@example.com", "password123", "Needs Healing")
r = client.post("/families", json={"name": "Demo Family (Sample Data)", "timezone": "UTC"}, headers=healed_headers)
assert r.status_code in (200, 201), r.text
r = client.get("/families/mine", headers=healed_headers)
assert r.status_code == 200, r.text
healed_name = r.json()[0]["name"]
print(f"Self-heal on GET /families/mine: family renamed to {healed_name!r} -- {'OK' if healed_name != 'Demo Family (Sample Data)' else 'FAILED, still contaminated'}")

print("\nSMOKE_FK_ENFORCED DONE")
