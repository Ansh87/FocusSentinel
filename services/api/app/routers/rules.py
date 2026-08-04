from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import require_parent

router = APIRouter(prefix="/rules", tags=["rules"])


def _to_rule_out(db: Session, rule: models.ScreenTimeRule) -> schemas.RuleOut:
    category_key = None
    if rule.scope_category_id:
        category = db.get(models.ActivityCategory, rule.scope_category_id)
        category_key = category.key if category else None

    website_ids = [rw.website_id for rw in db.query(models.RuleWebsite).filter_by(rule_id=rule.id).all()]
    if rule.scope_website_id and rule.scope_website_id not in website_ids:
        website_ids.append(rule.scope_website_id)
    websites = []
    if website_ids:
        rows = db.query(models.Website).filter(models.Website.id.in_(website_ids)).all()
        websites = [
            schemas.WebsiteOut(
                id=w.id,
                domain=w.domain,
                url_pattern=w.url_pattern,
                label=w.label,
                category_id=w.category_id,
                source=w.source,
                is_custom=w.family_id is not None,
            )
            for w in rows
        ]

    return schemas.RuleOut(
        id=rule.id,
        student_id=rule.student_id,
        name=rule.name,
        scope_type=rule.scope_type,
        scope_category_key=category_key,
        websites=websites,
        daily_limit_minutes=rule.daily_limit_minutes,
        warning_one_at_minutes=rule.warning_one_at_minutes,
        warning_two_after_additional_minutes=rule.warning_two_after_additional_minutes,
        block_after_warning_two_seconds=rule.block_after_warning_two_seconds,
        days_of_week=rule.days_of_week,
        reset_time=rule.reset_time,
        active=rule.active,
    )


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

    websites = []
    if payload.website_ids:
        websites = db.query(models.Website).filter(models.Website.id.in_(payload.website_ids)).all()
        found_ids = {w.id for w in websites}
        missing = set(payload.website_ids) - found_ids
        if missing:
            raise HTTPException(400, f"Unknown website id(s): {', '.join(sorted(missing))}")
        not_visible = [w.id for w in websites if w.family_id is not None and w.family_id != student.family_id]
        if not_visible:
            raise HTTPException(403, "One or more selected websites do not belong to this family")

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
    for website in websites:
        db.add(models.RuleWebsite(rule_id=rule.id, website_id=website.id))
    db.add(
        models.AuditLog(
            family_id=student.family_id,
            actor_user_id=user.id,
            actor_type="parent",
            action="rule.created",
            target_type="screen_time_rule",
            target_id=rule.id,
            event_metadata={
                "name": rule.name,
                "daily_limit_minutes": rule.daily_limit_minutes,
                "website_ids": [w.id for w in websites],
            },
        )
    )
    db.commit()
    db.refresh(rule)
    return _to_rule_out(db, rule)


@router.put("/{rule_id}", response_model=schemas.RuleOut)
def update_rule(rule_id: str, payload: schemas.RuleUpdate, db: Session = Depends(get_db), user: models.User = Depends(require_parent)):
    rule = db.get(models.ScreenTimeRule, rule_id)
    if not rule:
        raise HTTPException(404, "Rule not found")

    fields = payload.model_dump(exclude_unset=True)
    website_ids = fields.pop("website_ids", None)
    scope_category_key = fields.pop("scope_category_key", None)
    student_id = fields.pop("student_id", None)

    if student_id is not None:
        student = db.get(models.Student, student_id)
        if not student:
            raise HTTPException(404, "Student not found")
        rule.student_id = student.id
        rule.family_id = student.family_id

    if scope_category_key is not None:
        category = db.query(models.ActivityCategory).filter_by(key=scope_category_key).first()
        if not category:
            raise HTTPException(400, f"Unknown category key: {scope_category_key}")
        rule.scope_category_id = category.id
        rule.scope_type = "category"
        # Switching a rule to a whole-category scope clears any website
        # selection it previously had, so the two scopes never coexist in
        # a way that would make find_active_rule's priority ambiguous.
        rule.scope_website_id = None
        db.query(models.RuleWebsite).filter_by(rule_id=rule.id).delete()

    if website_ids is not None:
        # website_ids isn't a plain column on ScreenTimeRule — it's a
        # separate join table — so it's handled here instead of via the
        # generic setattr loop below, by replacing the rule's full website
        # set (delete-then-recreate is simplest and safe since RuleWebsite
        # carries no independent state of its own).
        websites = db.query(models.Website).filter(models.Website.id.in_(website_ids)).all()
        found_ids = {w.id for w in websites}
        missing = set(website_ids) - found_ids
        if missing:
            raise HTTPException(400, f"Unknown website id(s): {', '.join(sorted(missing))}")
        not_visible = [w.id for w in websites if w.family_id is not None and w.family_id != rule.family_id]
        if not_visible:
            raise HTTPException(403, "One or more selected websites do not belong to this family")
        db.query(models.RuleWebsite).filter_by(rule_id=rule.id).delete()
        for website in websites:
            db.add(models.RuleWebsite(rule_id=rule.id, website_id=website.id))
        if website_ids:
            rule.scope_type = "website"
            rule.scope_category_id = None

    for field, value in fields.items():
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
    return _to_rule_out(db, rule)


@router.delete("/{rule_id}", status_code=204)
def delete_rule(rule_id: str, db: Session = Depends(get_db), user: models.User = Depends(require_parent)):
    rule = db.get(models.ScreenTimeRule, rule_id)
    if not rule:
        raise HTTPException(404, "Rule not found")

    db.query(models.RuleWebsite).filter_by(rule_id=rule.id).delete()
    db.query(models.WarningEvent).filter_by(rule_id=rule.id).delete()
    db.query(models.RestrictionEvent).filter_by(rule_id=rule.id).delete()
    # Extension requests keep their history rather than being deleted — just
    # detach them from the rule that no longer exists.
    db.query(models.ExtensionRequest).filter_by(rule_id=rule.id).update({"rule_id": None})

    db.add(
        models.AuditLog(
            family_id=rule.family_id,
            actor_user_id=user.id,
            actor_type="parent",
            action="rule.deleted",
            target_type="screen_time_rule",
            target_id=rule.id,
            event_metadata={"name": rule.name},
        )
    )
    db.delete(rule)
    db.commit()
    return None


@router.get("/student/{student_id}", response_model=list[schemas.RuleOut])
def list_rules(student_id: str, db: Session = Depends(get_db), user: models.User = Depends(require_parent)):
    rules = db.query(models.ScreenTimeRule).filter_by(student_id=student_id).all()
    return [_to_rule_out(db, r) for r in rules]
