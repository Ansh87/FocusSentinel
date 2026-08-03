from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user, require_parent
from ..notifications import enqueue_notification

router = APIRouter(prefix="/extension-requests", tags=["extension-requests"])


@router.get("", response_model=list[schemas.ExtensionRequestOut])
def list_extension_requests(student_id: str, status: str | None = None, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    query = db.query(models.ExtensionRequest).filter_by(student_id=student_id)
    if status:
        query = query.filter_by(status=status)
    return query.order_by(models.ExtensionRequest.created_at.desc()).all()


@router.post("", response_model=schemas.ExtensionRequestOut, status_code=201)
def create_extension_request(payload: schemas.ExtensionRequestCreate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
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
        },
    )
    db.commit()
    db.refresh(req)
    return req


@router.post("/{request_id}/approve", response_model=schemas.ExtensionRequestOut)
def approve_extension_request(request_id: str, decision: schemas.ExtensionDecision, db: Session = Depends(get_db), user: models.User = Depends(require_parent)):
    req = db.get(models.ExtensionRequest, request_id)
    if not req:
        raise HTTPException(404, "Extension request not found")
    if req.status != "pending":
        raise HTTPException(409, f"Request already {req.status}")

    minutes = 24 * 60 if decision.rest_of_day else (decision.minutes or req.requested_minutes or 0)
    req.status = "approved"
    req.decided_by = user.id
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
            actor_user_id=user.id,
            actor_type="parent",
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
    db.commit()
    db.refresh(req)
    return req


@router.post("/{request_id}/deny", response_model=schemas.ExtensionRequestOut)
def deny_extension_request(request_id: str, db: Session = Depends(get_db), user: models.User = Depends(require_parent)):
    req = db.get(models.ExtensionRequest, request_id)
    if not req:
        raise HTTPException(404, "Extension request not found")
    if req.status != "pending":
        raise HTTPException(409, f"Request already {req.status}")

    req.status = "denied"
    req.decided_by = user.id
    req.decided_at = datetime.utcnow()

    student = db.get(models.Student, req.student_id)
    db.add(
        models.AuditLog(
            family_id=student.family_id if student else None,
            actor_user_id=user.id,
            actor_type="parent",
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
    db.commit()
    db.refresh(req)
    return req
