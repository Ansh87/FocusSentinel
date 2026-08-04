"""Computes first-time setup progress for a family, live from real data
rather than a set of stored booleans that could drift out of sync. The
wizard has 5 screens (family profile, student, websites, rule, device), but
website selection isn't a separately persisted milestone -- a parent picks
websites *while* creating the first rule, so it's folded into
`first_rule_created` here. See models.FamilyOnboardingState for the one
piece of state that genuinely can't be derived (when the wizard was
started/finished, and whether the reminder banner or device step were
explicitly dismissed)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from . import models


def get_or_create_onboarding_state(db: Session, family_id: str) -> models.FamilyOnboardingState:
    state = db.get(models.FamilyOnboardingState, family_id)
    if not state:
        state = models.FamilyOnboardingState(family_id=family_id)
        db.add(state)
        db.flush()
    return state


def compute_setup_status(db: Session, family_id: str) -> dict:
    state = db.get(models.FamilyOnboardingState, family_id)

    student_count = db.query(models.Student).filter_by(family_id=family_id).count()
    rule_count = db.query(models.ScreenTimeRule).filter_by(family_id=family_id).count()
    student_ids = [s.id for s in db.query(models.Student.id).filter_by(family_id=family_id).all()]
    device_count = (
        db.query(models.Device).filter(models.Device.student_id.in_(student_ids)).count() if student_ids else 0
    )

    family_profile_completed = True  # this endpoint only runs for a family that already exists
    student_added = student_count > 0
    first_rule_created = rule_count > 0
    device_connected = device_count > 0
    device_connect_skipped = state.device_connect_skipped if state else False

    # Device connection is recommended, not required -- matches the product
    # rule "consider setup complete once there's a family, a student, and a
    # rule." The 4th milestone still shows in the UI so a parent can see it's
    # outstanding, it just doesn't block `is_complete`.
    required_steps = [family_profile_completed, student_added, first_rule_created]
    optional_steps = [device_connected or device_connect_skipped]
    completed_steps = sum(required_steps) + sum(optional_steps)
    is_complete = all(required_steps)

    remaining: list[str] = []
    if not student_added:
        remaining.append("Add your first student")
    if not first_rule_created:
        remaining.append("Choose websites and create your first rule")
    if not device_connected and not device_connect_skipped:
        remaining.append("Connect a student device")

    return {
        "family_id": family_id,
        "started_at": state.started_at if state else None,
        "completed_at": state.completed_at if state else None,
        "family_profile_completed": family_profile_completed,
        "student_added": student_added,
        "first_rule_created": first_rule_created,
        "device_connected": device_connected,
        "device_connect_skipped": device_connect_skipped,
        "completed_steps": completed_steps,
        "total_steps": 4,
        "is_complete": is_complete,
        "remaining_steps": remaining,
        "reminder_dismissed_until": state.reminder_dismissed_until if state else None,
    }


def mark_completed_if_ready(db: Session, family_id: str) -> None:
    """Called after any mutation that could complete setup (adding a
    student, creating a rule) so `completed_at` gets stamped the moment the
    family first satisfies the requirement, rather than only when someone
    happens to poll the status endpoint."""
    status = compute_setup_status(db, family_id)
    if not status["is_complete"]:
        return
    state = get_or_create_onboarding_state(db, family_id)
    if not state.completed_at:
        state.completed_at = datetime.utcnow()
