"""Seeds demo data: one family, one parent account, one student, a browser
extension device, a short-form-video limit, a notification recipient, and
the global classification catalog (categories + well-known websites).

Run after the API's tables exist (either via `Base.metadata.create_all`, which
happens automatically the first time the API boots, or via the SQL migration
in database/migrations/0001_init.sql against Postgres):

    cd services/api
    DATABASE_URL=<same URL the API uses> python ../../database/seed/seed.py

Demo login (also printed at the end of the run):
    parent@focussentinel.demo / demo-password-123
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "services", "api"))

from app.database import Base, SessionLocal, engine  # noqa: E402
from app import models  # noqa: E402
from app.security import generate_device_token, hash_password  # noqa: E402


CATEGORIES = [
    ("games", "Games"),
    ("short_form_video", "Short-form video"),
    ("social_media", "Social media"),
    ("entertainment_video", "Entertainment video"),
    ("messaging", "Messaging"),
    ("educational", "Educational"),
    ("productivity", "Productivity"),
    ("creative_work", "Creative work"),
    ("reading_research", "Reading and research"),
    ("other", "Other"),
]

CATALOG_WEBSITES = [
    ("tiktok.com", None, "TikTok", "short_form_video", "limited"),
    ("youtube.com", "/shorts", "YouTube Shorts", "short_form_video", "limited"),
    ("instagram.com", "/reels", "Instagram Reels", "short_form_video", "limited"),
    ("facebook.com", "/reel", "Facebook Reels", "short_form_video", "limited"),
    ("instagram.com", None, "Instagram", "social_media", "limited"),
    ("facebook.com", None, "Facebook", "social_media", "limited"),
    ("twitch.tv", None, "Twitch", "entertainment_video", "limited"),
    ("discord.com", None, "Discord", "messaging", "neutral"),
    ("reddit.com", None, "Reddit", "social_media", "limited"),
    ("netflix.com", None, "Netflix", "entertainment_video", "limited"),
    ("youtube.com", None, "YouTube", "entertainment_video", "neutral"),
]


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        category_by_key = {}
        for key, label in CATEGORIES:
            existing = db.query(models.ActivityCategory).filter_by(key=key).first()
            if existing:
                category_by_key[key] = existing
                continue
            cat = models.ActivityCategory(key=key, label=label)
            db.add(cat)
            db.flush()
            category_by_key[key] = cat

        for domain, url_pattern, label, category_key, classification in CATALOG_WEBSITES:
            exists = (
                db.query(models.Website)
                .filter_by(family_id=None, domain=domain, url_pattern=url_pattern)
                .first()
            )
            if exists:
                continue
            db.add(
                models.Website(
                    family_id=None,
                    domain=domain,
                    url_pattern=url_pattern,
                    label=label,
                    category_id=category_by_key[category_key].id,
                    classification=classification,
                    source="catalog",
                )
            )

        parent = db.query(models.User).filter_by(email="parent@focussentinel.demo").first()
        if parent is None:
            parent = models.User(
                email="parent@focussentinel.demo",
                password_hash=hash_password("demo-password-123"),
                role="parent",
                display_name="Demo Parent",
            )
            db.add(parent)
            db.flush()

        family = db.query(models.Family).filter_by(name="Demo Family").first()
        if family is None:
            family = models.Family(name="Demo Family", timezone="America/Chicago")
            db.add(family)
            db.flush()
            db.add(models.FamilyMember(family_id=family.id, user_id=parent.id, role="parent"))

        student = db.query(models.Student).filter_by(family_id=family.id, display_name="Demo Student").first()
        if student is None:
            student = models.Student(
                family_id=family.id,
                display_name="Demo Student",
                age_range="13_15",
                timezone="America/Chicago",
            )
            db.add(student)
            db.flush()

        device = db.query(models.Device).filter_by(student_id=student.id, name="Demo Chrome Extension").first()
        device_token_plaintext = None
        if device is None:
            device_token_plaintext, token_hash = generate_device_token()
            device = models.Device(
                student_id=student.id,
                device_type="browser_extension",
                name="Demo Chrome Extension",
                device_token_hash=token_hash,
                status="active",
            )
            db.add(device)
            db.flush()

        rule = db.query(models.ScreenTimeRule).filter_by(student_id=student.id, name="Short-form video — demo limit").first()
        if rule is None:
            rule = models.ScreenTimeRule(
                family_id=family.id,
                student_id=student.id,
                name="Short-form video — demo limit",
                scope_type="category",
                scope_category_id=category_by_key["short_form_video"].id,
                days_of_week=[0, 1, 2, 3, 4, 5, 6],
                daily_limit_minutes=2,
                warning_one_at_minutes=2,
                warning_two_after_additional_minutes=1,
                block_after_warning_two_seconds=30,
            )
            db.add(rule)

        recipient = db.query(models.NotificationRecipient).filter_by(family_id=family.id, email="parent@focussentinel.demo").first()
        if recipient is None:
            recipient = models.NotificationRecipient(
                family_id=family.id,
                name="Demo Parent",
                relationship="parent",
                email="parent@focussentinel.demo",
                preferred_channels=["email"],
                severity_preference="all",
                verified=True,
            )
            db.add(recipient)

        db.commit()

        print("Seed complete.")
        print(f"  Family ID:  {family.id}")
        print(f"  Student ID: {student.id}")
        print(f"  Device ID:  {device.id}")
        if device_token_plaintext:
            print(f"  Device token (save this, shown once): {device_token_plaintext}")
        print("  Parent login: parent@focussentinel.demo / demo-password-123")
    finally:
        db.close()


if __name__ == "__main__":
    main()
