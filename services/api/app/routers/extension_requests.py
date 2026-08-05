from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import ensure_can_manage_student, ensure_own_student_or_parent, get_current_user
from ..notifications import create_sms_decision_links, enqueue_direct_sms, enqueue_notification

router = APIRouter(prefix="/extension-requests", tags=["extension-requests"])


def approve_request_internal(
    db: Session,
    req: models.ExtensionRequest,
    *,
    user_id: str | None,
    actor_type: str,
    minutes: int,
) -> None:
    """Shared by the parent-facing HTTP endpoint and the SMS webhook (a
    parent texting back "YES") so the two paths can never drift apart on
    what "approved" actually does -- lift the restriction, stamp the
    decision, log it, notify the student."""
    req.status = "approved"
    req.decided_by = user_id
    req.decided_minutes = minutes
    req.decided_at = datetime.utcnow()

    if req.restriction_event_id:
        restriction = db.get(models.RestrictionEvent, req.restriction_event_id)
        if restriction and restriction.active:
            restriction.active = False
            restriction.lifted_at = datetime.utcnow()
            restriction.lifted_reason = "extension_approved"

    student = db.get(models.Student, req.student_id)
    db.add(
        models.AuditLog(
            family_id=student.family_id if student else None,
            actor_user_id=user_id,
            actor_type=actor_type,
            action="extension_request.approved",
            target_type="extension_request",
            target_id=req.id,
            event_metadata={"minutes": minutes},
        )
    )
    if student:
        enqueue_notification(
            db,
            family_id=student.family_id,
            student_id=student.id,
            event_type="extension_approved",
            rule_id=req.rule_id,
            payload={"minutes": minutes},
        )
        _notify_student_of_decision(db, student, event_type="extension_approved_student", payload={"minutes": minutes})


def _notify_student_of_decision(db: Session, student: models.Student, *, event_type: str, payload: dict) -> None:
    """Texts the requesting student's own phone (if they have one on file)
    once their extension request is decided -- regardless of whether the
    parent decided via the dashboard buttons or by replying YES/NO to a
    text. Without this, a request texted in gets a reply to the *parent's*
    phone but the kid who's actually waiting never hears back unless they
    happen to check the dashboard."""
    phone = db.query(models.StudentPhone).filter_by(student_id=student.id).first()
    if not phone:
        return
    enqueue_direct_sms(
        db,
        family_id=student.family_id,
        to_phone=phone.phone_number,
        event_type=event_type,
        payload={**payload, "student_name": student.display_name},
    )


def deny_request_internal(db: Session, req: models.ExtensionRequest, *, user_id: str | None, actor_type: str) -> None:
    req.status = "denied"
    req.decided_by = user_id
    req.decided_at = datetime.utcnow()

    student = db.get(models.Student, req.student_id)
    db.add(
        models.AuditLog(
            family_id=student.family_id if student else None,
            actor_user_id=user_id,
            actor_type=actor_type,
            action="extension_request.denied",
            target_type="extension_request",
            target_id=req.id,
        )
    )
    if student:
        enqueue_notification(
            db,
            family_id=student.family_id,
            student_id=student.id,
            event_type="extension_denied",
            rule_id=req.rule_id,
            payload={},
        )
        _notify_student_of_decision(db, student, event_type="extension_denied_student", payload={})


@router.get("", response_model=list[schemas.ExtensionRequestOut])
def list_extension_requests(student_id: str, status: str | None = None, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    ensure_own_student_or_parent(db, user, student_id)
    query = db.query(models.ExtensionRequest).filter_by(student_id=student_id)
    if status:
        query = query.filter_by(status=status)
    return query.order_by(models.ExtensionRequest.created_at.desc()).all()


@router.post("", response_model=schemas.ExtensionRequestOut, status_code=201)
def create_extension_request(payload: schemas.ExtensionRequestCreate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    ensure_own_student_or_parent(db, user, payload.student_id)
    student = db.get(models.Student, payload.student_id)
    if not student:
        raise HTTPException(404, "Student not found")

    req = models.ExtensionRequest(
        student_id=payload.student_id,
        restriction_event_id=payload.restriction_event_id,
        rule_id=payload.rule_id,
        requested_minutes=payload.requested_minutes,
        reason_code=payload.reason_code,
        explanation=payload.explanation,
    )
    db.add(req)
    db.flush()

    sms_code = create_sms_decision_links(db, family_id=student.family_id, extension_request_id=req.id)

    enqueue_notification(
        db,
        family_id=student.family_id,
        student_id=student.id,
        event_type="extension_requested",
        rule_id=payload.rule_id,
        payload={
            "student_name": student.display_name,
            "requested_minutes": payload.requested_minutes,
            "reason_code": payload.reason_code,
            "explanation": payload.explanation,
            "sms_reply_hint": f" Reply YES {sms_code} or NO {sms_code} by text to decide now." if sms_code else "",
        },
    )
    db.commit()
    db.refresh(req)
    return req


@router.post("/grant", response_model=schemas.ExtensionRequestOut)
def grant_extension(payload: schemas.ExtensionGrantRequest, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Lets a parent (or an authorized sibling manager) proactively hand over
    extra time from the "Allow more time" action on a restriction card,
    without waiting on the student to have filed a request first. Creates
    the ExtensionRequest already approved, in one step, so it shows up in
    history the same way a student-initiated approval would."""
    student = db.get(models.Student, payload.student_id)
    if not student:
        raise HTTPException(404, "Student not found")
    ensure_can_manage_student(db, user, student.id)

    restriction = (
        db.query(models.RestrictionEvent)
        .filter_by(student_id=payload.student_id, rule_id=payload.rule_id, active=True)
        .order_by(models.RestrictionEvent.started_at.desc())
        .first()
    )
    req = models.ExtensionRequest(
        student_id=payload.student_id,
        restriction_event_id=restriction.id if restriction else None,
        rule_id=payload.rule_id,
        requested_minutes=payload.minutes,
        reason_code="other",
        explanation="Granted directly by parent.",
        status="approved",
        decided_by=user.id,
        decided_minutes=payload.minutes,
        decided_at=datetime.utcnow(),
    )
    db.add(req)
    db.flush()

    if restriction and restriction.active:
        restriction.active = False
        restriction.lifted_at = datetime.utcnow()
        restriction.lifted_reason = "extension_approved"

    actor_type = "parent" if user.role in ("parent", "admin") else "sibling_manager"
    db.add(
        models.AuditLog(
            family_id=student.family_id,
            actor_user_id=user.id,
            actor_type=actor_type,
            action="extension_request.granted",
            target_type="extension_request",
            target_id=req.id,
            event_metadata={"minutes": payload.minutes},
        )
    )
    enqueue_notification(
        db,
        family_id=student.family_id,
        student_id=student.id,
        event_type="extension_approved",
        rule_id=payload.rule_id,
        payload={"minutes": payload.minutes},
    )
    db.commit()
    db.refresh(req)
    return req


@router.post("/{request_id}/approve", response_model=schemas.ExtensionRequestOut)
def approve_extension_request(request_id: str, decision: schemas.ExtensionDecision, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    req = db.get(models.ExtensionRequest, request_id)
    if not req:
        raise HTTPException(404, "Extension request not found")
    ensure_can_manage_student(db, user, req.student_id)
    if req.status != "pending":
        raise HTTPException(409, f"Request already {req.status}")

    minutes = 24 * 60 if decision.rest_of_day else (decision.minutes or req.requested_minutes or 0)
    actor_type = "parent" if user.role in ("parent", "admin") else "sibling_manager"
    approve_request_internal(db, req, user_id=user.id, actor_type=actor_type, minutes=minutes)
    db.commit()
    db.refresh(req)
    return req


@router.post("/{request_id}/deny", response_model=schemas.ExtensionRequestOut)
def deny_extension_request(request_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    req = db.get(models.ExtensionRequest, request_id)
    if not req:
        raise HTTPException(404, "Extension request not found")
    ensure_can_manage_student(db, user, req.student_id)
    if req.status != "pending":
        raise HTTPException(409, f"Request already {req.status}")

    actor_type = "parent" if user.role in ("parent", "admin") else "sibling_manager"
    deny_request_internal(db, req, user_id=user.id, actor_type=actor_type)
    db.commit()
    db.refresh(req)
    return req
