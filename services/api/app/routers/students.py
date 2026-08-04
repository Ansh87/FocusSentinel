from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import cascade, models, schemas, setup_status
from ..database import get_db
from ..deps import active_sibling_grant, ensure_own_student_or_parent, get_current_user, require_parent
from ..security import hash_password
from ..usage_service import seconds_today_for_rule

router = APIRouter(prefix="/students", tags=["students"])


def _with_sibling_manager_flag(db: Session, student: models.Student) -> schemas.StudentOut:
    out = schemas.StudentOut.model_validate(student)
    grant = active_sibling_grant(db, student.family_id, student.id)
    out.is_sibling_manager = grant is not None
    out.sibling_manager_until = grant.expires_at if grant else None
    return out


@router.get("/me", response_model=schemas.StudentOut)
def my_student_profile(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    student = db.query(models.Student).filter_by(user_id=user.id).first()
    if not student:
        raise HTTPException(404, "No student profile is linked to this account.")
    return _with_sibling_manager_flag(db, student)


@router.post("", response_model=schemas.StudentOut, status_code=201)
def create_student(payload: schemas.StudentCreate, db: Session = Depends(get_db), user: models.User = Depends(require_parent)):
    membership = db.query(models.FamilyMember).filter_by(family_id=payload.family_id, user_id=user.id).first()
    if not membership:
        raise HTTPException(403, "Not a member of this family")
    student = models.Student(
        family_id=payload.family_id,
        display_name=payload.display_name,
        age_range=payload.age_range,
        timezone=payload.timezone,
    )
    db.add(student)
    db.flush()
    db.add(
        models.AuditLog(
            family_id=payload.family_id,
            actor_user_id=user.id,
            actor_type="parent",
            action="student.created",
            target_type="student",
            target_id=student.id,
        )
    )
    setup_status.mark_completed_if_ready(db, payload.family_id)
    db.commit()
    db.refresh(student)
    return student


@router.get("/family/{family_id}", response_model=list[schemas.StudentOut])
def list_students(family_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    students = db.query(models.Student).filter_by(family_id=family_id).all()
    return [_with_sibling_manager_flag(db, s) for s in students]


def _student_and_family(db: Session, student_id: str) -> tuple[models.Student, models.Family]:
    student = db.get(models.Student, student_id)
    if not student:
        raise HTTPException(404, "Student not found")
    return student, db.get(models.Family, student.family_id)


def _require_family_membership(db: Session, user: models.User, family_id: str) -> None:
    membership = db.query(models.FamilyMember).filter_by(family_id=family_id, user_id=user.id).first()
    if not membership:
        raise HTTPException(403, "Not a member of this family")


@router.delete("/{student_id}", status_code=200)
def delete_student(student_id: str, db: Session = Depends(get_db), user: models.User = Depends(require_parent)):
    """Removes a student profile and everything under it — rules, devices,
    usage/warning/restriction history, extension requests, and their own
    login if they have one. Cannot be undone; the frontend confirms with the
    parent before calling this."""
    student, family = _student_and_family(db, student_id)
    _require_family_membership(db, user, family.id)

    cascade.delete_students(db, [student_id])
    db.add(
        models.AuditLog(
            family_id=family.id,
            actor_user_id=user.id,
            actor_type="parent",
            action="student.deleted",
            target_type="student",
            target_id=student_id,
            event_metadata={"display_name": student.display_name},
        )
    )
    db.commit()
    return {"status": "student_deleted"}


@router.delete("/{student_id}/usage/history")
def clear_usage_history(student_id: str, db: Session = Depends(get_db), user: models.User = Depends(require_parent)):
    """Wipes recorded activity (raw usage events and the daily rollups the
    Activity History page reads) for this student. Leaves the student
    profile, rules, and devices untouched — this is "clear history," not
    "remove this kid.\""""
    student, family = _student_and_family(db, student_id)
    _require_family_membership(db, user, family.id)

    db.query(models.UsageEvent).filter_by(student_id=student_id).delete(synchronize_session=False)
    db.query(models.DailyUsageTotal).filter_by(student_id=student_id).delete(synchronize_session=False)
    db.add(
        models.AuditLog(
            family_id=family.id,
            actor_user_id=user.id,
            actor_type="parent",
            action="student.history_cleared",
            target_type="student",
            target_id=student_id,
        )
    )
    db.commit()
    return {"status": "history_cleared"}


@router.post("/{student_id}/sibling-manager", response_model=schemas.SiblingManagerStatus)
def grant_sibling_manager(
    student_id: str,
    payload: schemas.SiblingManagerGrantRequest | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_parent),
):
    """Authorizes this student (typically the eldest) to manage screen-time
    rules and decide extension requests for their siblings in the same
    family. Requires the student to already have their own login — there's
    no way to delegate management to someone who can't sign in. Pass
    `hours` to make this a temporary grant (e.g. "cover for me for the
    weekend") that stops applying on its own once it expires — no need to
    remember to revoke it. Calling this again on an existing grant replaces
    its expiry, so extending or shortening a grant is the same call."""
    student, family = _student_and_family(db, student_id)
    _require_family_membership(db, user, family.id)
    if not student.user_id:
        raise HTTPException(400, "This student needs their own sign-in before they can manage siblings.")

    hours = payload.hours if payload else None
    expires_at = datetime.utcnow() + timedelta(hours=hours) if hours else None

    existing = db.query(models.SiblingManagerGrant).filter_by(family_id=family.id, manager_student_id=student_id).first()
    if existing:
        existing.expires_at = expires_at
        existing.granted_by = user.id
    else:
        db.add(
            models.SiblingManagerGrant(
                family_id=family.id, manager_student_id=student_id, granted_by=user.id, expires_at=expires_at
            )
        )
    db.add(
        models.AuditLog(
            family_id=family.id,
            actor_user_id=user.id,
            actor_type="parent",
            action="sibling_manager.granted",
            target_type="student",
            target_id=student_id,
            event_metadata={"hours": hours},
        )
    )
    db.commit()
    return schemas.SiblingManagerStatus(student_id=student_id, is_sibling_manager=True, expires_at=expires_at)


@router.delete("/{student_id}/sibling-manager", response_model=schemas.SiblingManagerStatus)
def revoke_sibling_manager(student_id: str, db: Session = Depends(get_db), user: models.User = Depends(require_parent)):
    student, family = _student_and_family(db, student_id)
    _require_family_membership(db, user, family.id)

    db.query(models.SiblingManagerGrant).filter_by(family_id=family.id, manager_student_id=student_id).delete(synchronize_session=False)
    db.add(
        models.AuditLog(
            family_id=family.id,
            actor_user_id=user.id,
            actor_type="parent",
            action="sibling_manager.revoked",
            target_type="student",
            target_id=student_id,
        )
    )
    db.commit()
    return schemas.SiblingManagerStatus(student_id=student_id, is_sibling_manager=False)


@router.post("/{student_id}/login", response_model=schemas.StudentLoginStatus)
def set_student_login(student_id: str, payload: schemas.StudentLoginCreate, db: Session = Depends(get_db), user: models.User = Depends(require_parent)):
    """Creates (or, called again, resets) a login for this student profile.
    A parent chooses the email and password directly here rather than the
    student self-registering, since there's no independent way to verify a
    minor's email ownership — the same reasoning device tokens use: shown
    once, parent-controlled, no email round-trip required."""
    student, family = _student_and_family(db, student_id)
    membership = db.query(models.FamilyMember).filter_by(family_id=family.id, user_id=user.id).first()
    if not membership:
        raise HTTPException(403, "Not a member of this family")

    existing_email_owner = db.query(models.User).filter_by(email=payload.email).first()
    if existing_email_owner and existing_email_owner.id != student.user_id:
        raise HTTPException(409, "That email is already used by another account")

    if student.user_id:
        login_user = db.get(models.User, student.user_id)
        login_user.email = payload.email
        login_user.password_hash = hash_password(payload.password)
    else:
        login_user = models.User(
            email=payload.email,
            password_hash=hash_password(payload.password),
            role="student",
            display_name=student.display_name,
        )
        db.add(login_user)
        db.flush()
        student.user_id = login_user.id

    db.add(
        models.AuditLog(
            family_id=family.id,
            actor_user_id=user.id,
            actor_type="parent",
            action="student.login_set",
            target_type="student",
            target_id=student.id,
        )
    )
    db.commit()
    return schemas.StudentLoginStatus(has_login=True, email=login_user.email)


@router.get("/{student_id}/login", response_model=schemas.StudentLoginStatus)
def get_student_login_status(student_id: str, db: Session = Depends(get_db), user: models.User = Depends(require_parent)):
    student, _family = _student_and_family(db, student_id)
    if not student.user_id:
        return schemas.StudentLoginStatus(has_login=False, email=None)
    login_user = db.get(models.User, student.user_id)
    return schemas.StudentLoginStatus(has_login=True, email=login_user.email if login_user else None)


@router.get("/{student_id}/usage/today", response_model=schemas.TodayUsageOut)
def usage_today(student_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    ensure_own_student_or_parent(db, user, student_id)
    student = db.get(models.Student, student_id)
    if not student:
        raise HTTPException(404, "Student not found")

    from zoneinfo import ZoneInfo

    today = datetime.now(ZoneInfo(student.timezone or "UTC")).date().isoformat()
    totals = db.query(models.DailyUsageTotal).filter_by(student_id=student_id, usage_date=today).all()
    by_category: dict[str, int] = {}
    for t in totals:
        cat = db.get(models.ActivityCategory, t.category_id) if t.category_id else None
        key = cat.key if cat else "uncategorized"
        by_category[key] = by_category.get(key, 0) + t.total_seconds

    # Computed the same way the rules engine evaluates each rule — combined
    # across every website a multi-website rule covers — so the dashboard's
    # progress bars are correct for both legacy category/single-website rules
    # and the new multi-website ones without duplicating matching logic in
    # the frontend.
    by_rule: dict[str, int] = {}
    active_rules = db.query(models.ScreenTimeRule).filter_by(student_id=student_id, active=True).all()
    for rule in active_rules:
        by_rule[rule.id] = seconds_today_for_rule(db, student_id, today, rule)

    day_start = datetime.fromisoformat(today)
    day_end = day_start + timedelta(days=1)
    warnings = (
        db.query(models.WarningEvent)
        .filter(
            models.WarningEvent.student_id == student_id,
            models.WarningEvent.occurred_at >= day_start,
            models.WarningEvent.occurred_at < day_end,
        )
        .all()
    )
    restrictions = db.query(models.RestrictionEvent).filter_by(student_id=student_id, active=True).all()

    return schemas.TodayUsageOut(
        student_id=student_id,
        date=today,
        total_seconds_by_category=by_category,
        total_seconds_by_rule=by_rule,
        active_warnings=[{"rule_id": w.rule_id, "level": w.level, "minutes_used": w.minutes_used} for w in warnings],
        active_restrictions=[{"rule_id": r.rule_id, "reason": r.reason, "scheduled_reset_at": r.scheduled_reset_at.isoformat()} for r in restrictions],
    )


@router.get("/{student_id}/usage/weekly")
def usage_weekly(student_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    ensure_own_student_or_parent(db, user, student_id)
    from zoneinfo import ZoneInfo

    student = db.get(models.Student, student_id)
    if not student:
        raise HTTPException(404, "Student not found")
    tz = ZoneInfo(student.timezone or "UTC")
    today = datetime.now(tz).date()
    days = [(today - timedelta(days=i)).isoformat() for i in range(7)]
    totals = db.query(models.DailyUsageTotal).filter(
        models.DailyUsageTotal.student_id == student_id,
        models.DailyUsageTotal.usage_date.in_(days),
    ).all()
    by_day: dict[str, int] = {d: 0 for d in days}
    for t in totals:
        by_day[t.usage_date] = by_day.get(t.usage_date, 0) + t.total_seconds
    return {"student_id": student_id, "daily_totals_seconds": by_day}


@router.get("/{student_id}/usage/history", response_model=schemas.UsageHistoryOut)
def usage_history(student_id: str, days: int = 7, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Per-day, per-category breakdown for the Activity History page — richer
    than usage/weekly's single daily total, since a parent reviewing history
    wants to know *what* was used, not just how long."""
    ensure_own_student_or_parent(db, user, student_id)
    from zoneinfo import ZoneInfo

    days = max(1, min(days, 90))
    student = db.get(models.Student, student_id)
    if not student:
        raise HTTPException(404, "Student not found")
    tz = ZoneInfo(student.timezone or "UTC")
    today = datetime.now(tz).date()
    date_list = [(today - timedelta(days=i)).isoformat() for i in range(days)]

    totals = (
        db.query(models.DailyUsageTotal)
        .filter(models.DailyUsageTotal.student_id == student_id, models.DailyUsageTotal.usage_date.in_(date_list))
        .all()
    )
    category_cache: dict[str, str] = {}

    def category_key(cat_id: str | None) -> str:
        if not cat_id:
            return "uncategorized"
        if cat_id not in category_cache:
            cat = db.get(models.ActivityCategory, cat_id)
            category_cache[cat_id] = cat.key if cat else "uncategorized"
        return category_cache[cat_id]

    by_date: dict[str, dict[str, int]] = {d: {} for d in date_list}
    for t in totals:
        key = category_key(t.category_id)
        by_date[t.usage_date][key] = by_date[t.usage_date].get(key, 0) + t.total_seconds

    days_out = [
        schemas.UsageHistoryDay(
            date=d,
            total_seconds=sum(by_date[d].values()),
            total_seconds_by_category=by_date[d],
        )
        for d in date_list
    ]
    return schemas.UsageHistoryOut(student_id=student_id, days=days_out)
