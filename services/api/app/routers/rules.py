from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import require_parent

router = APIRouter(prefix="/rules", tags=["rules"])


@router.post("", response_model=schemas.RuleOut, status_code=201)
def create_rule(payload: schemas.RuleCreate, db: Session = Depends(get_db), user: models.User = Depends(require_parent)):
    student = db.get(models.Student, payload.student_id)
    if not student:
        raise HTTPException(404, "Student not found")

    category_id = None
    if payload.scope_category_key:
        category = db.query(models.ActivityCategory).filter_by(key=payload.scope_category_key).first()
        if not category:
            raise HTTPException(400, f"Unknown category key: {payload.scope_category_key}")
        category_id = category.id

    rule = models.ScreenTimeRule(
        family_id=student.family_id,
        student_id=student.id,
        name=payload.name,
        scope_type=payload.scope_type,
        scope_category_id=category_id,
        scope_application_id=payload.scope_application_id,
        scope_website_id=payload.scope_website_id,
        scope_device_id=payload.scope_device_id,
        days_of_week=payload.days_of_week,
        allowed_start=payload.allowed_start,
        allowed_end=payload.allowed_end,
        daily_limit_minutes=payload.daily_limit_minutes,
        warning_one_at_minutes=payload.warning_one_at_minutes,
        warning_two_after_additional_minutes=payload.warning_two_after_additional_minutes,
        block_after_warning_two_seconds=payload.block_after_warning_two_seconds,
        reset_time=payload.reset_time,
        immediate_enforcement=payload.immediate_enforcement,
    )
    db.add(rule)
    db.flush()
    db.add(
        models.AuditLog(
            family_id=student.family_id,
            actor_user_id=user.id,
            actor_type="parent",
            action="rule.created",
            target_type="screen_time_rule",
            target_id=rule.id,
            event_metadata={"name": rule.name, "daily_limit_minutes": rule.daily_limit_minutes},
        )
    )
    db.commit()
    db.refresh(rule)
    return rule


@router.put("/{rule_id}", response_model=schemas.RuleOut)
def update_rule(rule_id: str, payload: schemas.RuleUpdate, db: Session = Depends(get_db), user: models.User = Depends(require_parent)):
    rule = db.get(models.ScreenTimeRule, rule_id)
    if not rule:
        raise HTTPException(404, "Rule not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(rule, field, value)
    db.add(
        models.AuditLog(
            family_id=rule.family_id,
            actor_user_id=user.id,
            actor_type="parent",
            action="rule.updated",
            target_type="screen_time_rule",
            target_id=rule.id,
            event_metadata=payload.model_dump(exclude_unset=True),
        )
    )
    db.commit()
    db.refresh(rule)
    return rule


@router.get("/student/{student_id}", response_model=list[schemas.RuleOut])
def list_rules(student_id: str, db: Session = Depends(get_db), user: models.User = Depends(require_parent)):
    return db.query(models.ScreenTimeRule).filter_by(student_id=student_id).all()
