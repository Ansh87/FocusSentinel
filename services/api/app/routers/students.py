from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user, require_parent

router = APIRouter(prefix="/students", tags=["students"])


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
    db.commit()
    db.refresh(student)
    return student


@router.get("/family/{family_id}", response_model=list[schemas.StudentOut])
def list_students(family_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return db.query(models.Student).filter_by(family_id=family_id).all()


@router.get("/{student_id}/usage/today", response_model=schemas.TodayUsageOut)
def usage_today(student_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
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
        active_warnings=[{"rule_id": w.rule_id, "level": w.level, "minutes_used": w.minutes_used} for w in warnings],
        active_restrictions=[{"rule_id": r.rule_id, "reason": r.reason, "scheduled_reset_at": r.scheduled_reset_at.isoformat()} for r in restrictions],
    )


@router.get("/{student_id}/usage/weekly")
def usage_weekly(student_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
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
