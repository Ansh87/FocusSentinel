"""Demo data for the public dashboard: lets a signed-in parent load a
self-contained sample family (own account, own family row, no shared state
with anyone else's data) and reset it back to a known-good state. Uses a
name marker ("Demo Family (Sample Data)") rather than a new database column
so this ships without an ALTER TABLE against the already-deployed production
schema — see docs/DEPLOYMENT.md for why `Base.metadata.create_all` can add
new tables but not new columns to existing ones.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import require_parent
from ..security import generate_device_token
from ..usage_service import evaluate_and_persist, upsert_daily_total

router = APIRouter(prefix="/demo", tags=["demo"])

DEMO_FAMILY_NAME = "Demo Family (Sample Data)"

# The one email the public login page's "Try the Interactive Demo" button
# signs into. Must always land on a fully populated dashboard — see
# ensure_demo_account_family below.
RESERVED_DEMO_EMAIL = "parent@focussentinel.demo"


def is_demo_family_name(name: str) -> bool:
    return name == DEMO_FAMILY_NAME


def _find_demo_family(db: Session, user_id: str):
    membership_family_ids = [
        m.family_id for m in db.query(models.FamilyMember).filter_by(user_id=user_id).all()
    ]
    if not membership_family_ids:
        return None
    return (
        db.query(models.Family)
        .filter(models.Family.id.in_(membership_family_ids), models.Family.name == DEMO_FAMILY_NAME)
        .first()
    )


def _delete_family_cascade(db: Session, family_id: str) -> None:
    """Deletes a family and everything under it, in FK-safe order. Only ever
    called on a family we've verified is the caller's own demo family."""
    student_ids = [s.id for s in db.query(models.Student).filter_by(family_id=family_id).all()]
    device_ids = (
        [d.id for d in db.query(models.Device).filter(models.Device.student_id.in_(student_ids)).all()]
        if student_ids
        else []
    )

    if device_ids:
        db.query(models.DeviceHealthEvent).filter(models.DeviceHealthEvent.device_id.in_(device_ids)).delete(synchronize_session=False)
        db.query(models.DevicePermission).filter(models.DevicePermission.device_id.in_(device_ids)).delete(synchronize_session=False)
    if student_ids:
        db.query(models.WarningEvent).filter(models.WarningEvent.student_id.in_(student_ids)).delete(synchronize_session=False)
        db.query(models.RestrictionEvent).filter(models.RestrictionEvent.student_id.in_(student_ids)).delete(synchronize_session=False)
        db.query(models.ExtensionRequest).filter(models.ExtensionRequest.student_id.in_(student_ids)).delete(synchronize_session=False)
        db.query(models.UsageEvent).filter(models.UsageEvent.student_id.in_(student_ids)).delete(synchronize_session=False)
        db.query(models.DailyUsageTotal).filter(models.DailyUsageTotal.student_id.in_(student_ids)).delete(synchronize_session=False)
    db.query(models.ScreenTimeRule).filter_by(family_id=family_id).delete(synchronize_session=False)
    db.query(models.NotificationEvent).filter_by(family_id=family_id).delete(synchronize_session=False)
    db.query(models.NotificationRecipient).filter_by(family_id=family_id).delete(synchronize_session=False)
    db.query(models.AuditLog).filter_by(family_id=family_id).delete(synchronize_session=False)
    if device_ids:
        db.query(models.Device).filter(models.Device.id.in_(device_ids)).delete(synchronize_session=False)
    if student_ids:
        db.query(models.Student).filter(models.Student.id.in_(student_ids)).delete(synchronize_session=False)
    db.query(models.FamilyMember).filter_by(family_id=family_id).delete(synchronize_session=False)
    db.query(models.Family).filter_by(id=family_id).delete(synchronize_session=False)
    db.commit()


def _get_or_create_category(db: Session, key: str, label: str) -> models.ActivityCategory:
    category = db.query(models.ActivityCategory).filter_by(key=key).first()
    if category is None:
        category = models.ActivityCategory(key=key, label=label)
        db.add(category)
        db.flush()
    return category


def _create_demo_family(db: Session, user: models.User):
    family = models.Family(name=DEMO_FAMILY_NAME, timezone="America/Chicago")
    db.add(family)
    db.flush()
    db.add(models.FamilyMember(family_id=family.id, user_id=user.id, role="parent"))

    student = models.Student(
        family_id=family.id, display_name="Alex", age_range="13_15", timezone="America/Chicago"
    )
    db.add(student)
    db.flush()

    _plain, token_hash = generate_device_token()
    device = models.Device(
        student_id=student.id,
        device_type="browser_extension",
        name="Alex's Chrome Extension",
        platform_identifier="Chrome",
        device_token_hash=token_hash,
        status="active",
        last_seen_at=datetime.utcnow() - timedelta(minutes=2),
    )
    db.add(device)
    db.flush()

    short_form = _get_or_create_category(db, "short_form_video", "Short-form video")
    games = _get_or_create_category(db, "games", "Games")

    rule_video = models.ScreenTimeRule(
        family_id=family.id,
        student_id=student.id,
        name="Short-form video limit",
        scope_type="category",
        scope_category_id=short_form.id if short_form else None,
        days_of_week=[0, 1, 2, 3, 4, 5, 6],
        daily_limit_minutes=30,
        warning_one_at_minutes=24,
        warning_two_after_additional_minutes=3,
        block_after_warning_two_seconds=60,
        reset_time="00:00",
        active=True,
    )
    rule_games = models.ScreenTimeRule(
        family_id=family.id,
        student_id=student.id,
        name="Gaming limit",
        scope_type="category",
        scope_category_id=games.id if games else None,
        days_of_week=[0, 1, 2, 3, 4, 5, 6],
        daily_limit_minutes=60,
        warning_one_at_minutes=48,
        warning_two_after_additional_minutes=6,
        block_after_warning_two_seconds=60,
        reset_time="00:00",
        active=True,
    )
    db.add_all([rule_video, rule_games])
    db.flush()
    db.commit()

    usage_date = datetime.utcnow().date().isoformat()

    def record_usage(identifier: str, category_id: str | None, minutes: int):
        seconds = minutes * 60
        db.add(
            models.UsageEvent(
                student_id=student.id,
                device_id=device.id,
                website_id=None,
                identifier=identifier,
                category_id=category_id,
                started_at=datetime.utcnow() - timedelta(minutes=minutes),
                ended_at=datetime.utcnow(),
                active_duration_seconds=seconds,
                classification_source="catalog",
                idempotency_key=f"demo-{uuid.uuid4()}",
            )
        )
        db.flush()
        upsert_daily_total(db, student.id, usage_date, category_id, None, None, seconds)
        db.commit()
        total_today = (
            db.query(models.DailyUsageTotal)
            .filter_by(student_id=student.id, usage_date=usage_date, category_id=category_id, application_id=None, website_id=None)
            .first()
        )
        evaluate_and_persist(
            db, student, device, identifier, category_id, None,
            total_today.total_seconds if total_today else seconds,
            usage_date=usage_date,
        )
        db.commit()

    # 25 of 30 minutes on short-form video -> crosses the 24-minute (80%) warning threshold.
    record_usage("tiktok.com", short_form.id if short_form else None, 25)
    # 10 of 60 minutes on games -> comfortably within limit, for visual contrast.
    record_usage("roblox.com", games.id if games else None, 10)

    # A pending request for more time, ahead of actually hitting the limit.
    db.add(
        models.ExtensionRequest(
            student_id=student.id,
            rule_id=rule_video.id,
            requested_minutes=15,
            reason_code="school",
            explanation="I need to finish a class video.",
            status="pending",
        )
    )
    db.commit()

    return family, student


def ensure_demo_account_family(db: Session, user: models.User) -> None:
    """The reserved public demo login must never look mostly empty to a
    first-time visitor or reviewer. Earlier deployments seeded this exact
    account (via database/seed/seed.py) with a thin single-rule "Demo
    Family" that predates DEMO_FAMILY_NAME and the Simulate/Reset
    controls — isDemoFamily() on the frontend only recognizes the newer
    name, so that old seed family renders as a bare, mostly-empty
    dashboard. Called on every login for this one address: cleans up any
    non-matching family still attached to the account, then makes sure the
    rich, fully-populated demo family exists. Idempotent — a no-op after
    the first run for any given account."""
    if user.email != RESERVED_DEMO_EMAIL:
        return
    memberships = db.query(models.FamilyMember).filter_by(user_id=user.id).all()
    for m in memberships:
        fam = db.get(models.Family, m.family_id)
        if fam and fam.name != DEMO_FAMILY_NAME:
            _delete_family_cascade(db, fam.id)
    if not _find_demo_family(db, user.id):
        _create_demo_family(db, user)


@router.post("/load")
def load_demo(db: Session = Depends(get_db), user: models.User = Depends(require_parent)):
    existing = _find_demo_family(db, user.id)
    if existing:
        student = db.query(models.Student).filter_by(family_id=existing.id).first()
        return {"family_id": existing.id, "student_id": student.id if student else None, "created": False}
    family, student = _create_demo_family(db, user)
    return {"family_id": family.id, "student_id": student.id, "created": True}


@router.post("/reset")
def reset_demo(db: Session = Depends(get_db), user: models.User = Depends(require_parent)):
    existing = _find_demo_family(db, user.id)
    if existing:
        _delete_family_cascade(db, existing.id)
    family, student = _create_demo_family(db, user)
    return {"family_id": family.id, "student_id": student.id, "created": True}


@router.post("/simulate")
def simulate_activity(db: Session = Depends(get_db), user: models.User = Depends(require_parent)):
    """Drives the *real* rules engine and warning/restriction/extension-request
    pipeline against the demo family only — never a real family — so the demo
    walkthrough (usage climbing -> first warning -> final warning ->
    restricted -> extension requested) is genuine backend behavior, just
    triggered on demand instead of waiting on real browsing. The frontend is
    responsible for labeling this clearly as "Demo simulation."
    """
    family = _find_demo_family(db, user.id)
    if not family:
        raise HTTPException(404, "Load the demo family first.")

    student = db.query(models.Student).filter_by(family_id=family.id).first()
    device = db.query(models.Device).filter_by(student_id=student.id).first() if student else None
    rule = db.query(models.ScreenTimeRule).filter_by(family_id=family.id, name="Gaming limit").first()
    if not student or not device or not rule:
        raise HTTPException(400, "Demo data is incomplete — reset the demo and try again.")

    games = _get_or_create_category(db, "games", "Games")
    usage_date = datetime.utcnow().date().isoformat()

    current_total = (
        db.query(models.DailyUsageTotal)
        .filter_by(student_id=student.id, usage_date=usage_date, category_id=games.id, application_id=None, website_id=None)
        .first()
    )
    current_seconds = current_total.total_seconds if current_total else 0

    steps = []
    # Checkpoints chosen relative to this rule's actual thresholds (limit=60,
    # warning_one=48, warning_two=54) so the sequence reliably passes through
    # progress -> first warning -> final warning -> restricted.
    for target_minutes in (35, 49, 55, 62):
        target_seconds = target_minutes * 60
        delta = target_seconds - current_seconds
        if delta <= 0:
            continue
        db.add(
            models.UsageEvent(
                student_id=student.id,
                device_id=device.id,
                website_id=None,
                identifier="roblox.com",
                category_id=games.id,
                started_at=datetime.utcnow(),
                ended_at=datetime.utcnow(),
                active_duration_seconds=delta,
                classification_source="catalog",
                idempotency_key=f"demo-sim-{uuid.uuid4()}",
            )
        )
        db.flush()
        upsert_daily_total(db, student.id, usage_date, games.id, None, None, delta)
        db.commit()
        current_seconds = target_seconds
        result = evaluate_and_persist(db, student, device, "roblox.com", games.id, None, current_seconds, usage_date=usage_date)
        db.commit()
        steps.append(result)
        if result["level"] == "restricted":
            break

    extension_request_created = False
    already_pending = (
        db.query(models.ExtensionRequest)
        .filter_by(student_id=student.id, rule_id=rule.id, status="pending")
        .first()
    )
    if not already_pending:
        restriction = (
            db.query(models.RestrictionEvent)
            .filter_by(student_id=student.id, rule_id=rule.id, active=True)
            .order_by(models.RestrictionEvent.started_at.desc())
            .first()
        )
        db.add(
            models.ExtensionRequest(
                student_id=student.id,
                restriction_event_id=restriction.id if restriction else None,
                rule_id=rule.id,
                requested_minutes=15,
                reason_code="friends",
                explanation="Almost done with a round — can I get a few more minutes?",
                status="pending",
            )
        )
        db.commit()
        extension_request_created = True

    return {"steps": steps, "extension_request_created": extension_request_created}
