from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from .. import models, schemas
from ..config import settings
from ..database import get_db
from ..deps import ensure_can_manage_student, ensure_own_student_or_parent, get_current_user
from ..notifications import enqueue_direct_email, enqueue_notification
from ..security import create_extension_action_token, decode_token

router = APIRouter(prefix="/extension-requests", tags=["extension-requests"])

DEFAULT_EXTENSION_MINUTES = 15


def approve_request_internal(
    db: Session,
    req: models.ExtensionRequest,
    *,
    user_id: str | None,
    actor_type: str,
    minutes: int,
) -> None:
    """Shared by the parent-facing HTTP endpoint and the email magic-link
    endpoint (a parent tapping "Approve" from their phone) so the two paths
    can never drift apart on what "approved" actually does -- lift the
    restriction, stamp the decision, log it, notify the family."""
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


def _parent_emails(db: Session, family_id: str) -> list[str]:
    """Every parent's login email in this family -- the destination for the
    approve/deny action email sent when a student requests more time. Uses
    each parent's own account email rather than the separate
    NotificationRecipient contact list, so a parent gets this with zero
    setup the moment they create their account."""
    rows = (
        db.query(models.User.email)
        .join(models.FamilyMember, models.FamilyMember.user_id == models.User.id)
        .filter(models.FamilyMember.family_id == family_id, models.FamilyMember.role == "parent")
        .all()
    )
    return [r[0] for r in rows if r[0]]


def _send_approval_email(db: Session, req: models.ExtensionRequest, student: models.Student) -> None:
    """Emails every parent in the family a one-tap Approve/Deny link for
    this specific request, so a parent doesn't have to be looking at the
    dashboard to respond quickly -- see GET /decide below for what the
    links actually do. Delivery still depends on a real email_provider
    being configured for notification-worker; the 'console' default just
    logs it, same as every other notification in this app."""
    token = create_extension_action_token(req.id)
    base = settings.public_api_base_url.rstrip("/")
    approve_url = f"{base}/extension-requests/decide?token={token}&action=approve"
    deny_url = f"{base}/extension-requests/decide?token={token}&action=deny"
    for email in _parent_emails(db, student.family_id):
        enqueue_direct_email(
            db,
            to_email=email,
            event_type="extension_request_approval",
            payload={
                "student_name": student.display_name,
                "requested_minutes": req.requested_minutes,
                "reason_code": req.reason_code,
                "explanation": req.explanation,
                "approve_url": approve_url,
                "deny_url": deny_url,
            },
            dedup_key=f"extension_request_approval:{req.id}:{email}",
        )


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

    _send_approval_email(db, req, student)

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


def _decision_page(title: str, message: str) -> str:
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — FocusSentinel</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background:#f5f6f8;
          margin:0; padding:48px 20px; color:#1f2430; }}
  .card {{ max-width:420px; margin:0 auto; background:#fff; border-radius:14px; padding:32px 26px;
           box-shadow:0 1px 4px rgba(0,0,0,0.08); text-align:center; }}
  h1 {{ font-size:21px; margin:0 0 10px; }}
  p {{ font-size:15px; line-height:1.55; color:#4a5060; margin:0; }}
</style></head>
<body><div class="card"><h1>{title}</h1><p>{message}</p></div></body></html>"""


@router.get("/decide", response_class=HTMLResponse)
def decide_extension_request_by_token(token: str, action: str, db: Session = Depends(get_db)):
    """Lets a parent approve or deny straight from the link in their
    approval email -- no login required. Protected by a short-lived,
    single-purpose JWT (see security.create_extension_action_token) rather
    than a session; a token for an already-decided request (clicked twice,
    or the other link clicked after this one) just shows a friendly
    "already decided" page instead of double-applying anything, since that
    check is the same `status != "pending"` guard the authenticated
    endpoints above already use."""
    if action not in ("approve", "deny"):
        raise HTTPException(400, "Invalid action")

    data = decode_token(token)
    if not data or data.get("type") != "extension_action":
        return HTMLResponse(_decision_page(
            "Link expired",
            "This approve/deny link is invalid or has expired. Please open the FocusSentinel dashboard instead.",
        ))

    req = db.get(models.ExtensionRequest, data["sub"])
    if not req:
        return HTMLResponse(_decision_page("Request not found", "This extension request no longer exists."))
    if req.status != "pending":
        return HTMLResponse(_decision_page(
            "Already decided",
            f"This request was already {req.status}. No further action is needed.",
        ))

    student = db.get(models.Student, req.student_id)
    student_name = student.display_name if student else "your student"

    if action == "approve":
        minutes = req.requested_minutes or DEFAULT_EXTENSION_MINUTES
        approve_request_internal(db, req, user_id=None, actor_type="parent", minutes=minutes)
        db.commit()
        return HTMLResponse(_decision_page("Approved", f"You approved {minutes} more minutes for {student_name}."))

    deny_request_internal(db, req, user_id=None, actor_type="parent")
    db.commit()
    return HTMLResponse(_decision_page("Denied", f"You denied the extension request for {student_name}."))
