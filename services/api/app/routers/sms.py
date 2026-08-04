"""Two-way SMS: a student can text FocusSentinel to request more time, and
a parent can reply YES/NO to a pending request by text instead of opening
the dashboard.

This only covers the *inbound* side and the API-level bookkeeping. Actually
sending texts (both the "your kid wants more time" alert and this module's
own instant replies) still goes through the same real, provider-backed path
as every other notification in this app: notification-worker's twilio_sms
adapter, gated behind TWILIO_ACCOUNT_SID/TWILIO_AUTH_TOKEN/TWILIO_FROM_NUMBER
(see services/notification-worker/app/config.py) and defaulting to a
'console' adapter that just logs instead of sending until those are set --
see docs/KNOWN_LIMITATIONS.md. The one exception is this router's own
immediate TwiML reply to whoever just texted in, which Twilio delivers
directly without going through the worker at all.

Twilio (or any compatible provider) should be configured to POST inbound
messages as application/x-www-form-urlencoded to:
    POST /sms/inbound?token=<SMS_WEBHOOK_TOKEN>
"""
from __future__ import annotations

import re
from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Response
from sqlalchemy.orm import Session

from .. import models, schemas
from ..config import settings
from ..database import get_db
from ..deps import require_parent
from ..notifications import create_sms_decision_links, enqueue_notification
from ..phone import normalize_phone
from .extension_requests import approve_request_internal, deny_request_internal

router = APIRouter(prefix="/sms", tags=["sms"])

DEFAULT_EXTENSION_MINUTES = 15


def _twiml(message: str) -> Response:
    body = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{body}</Message></Response>'
    return Response(content=xml, media_type="application/xml")


def _parse_minutes(body: str) -> int | None:
    match = re.search(r"\d+", body)
    return int(match.group()) if match else None


def _classify_decision(body: str) -> str | None:
    word = body.strip().split()[0].upper() if body.strip() else ""
    word = re.sub(r"[^\w]", "", word)
    if word in ("YES", "Y", "APPROVE", "APPROVED", "OK", "OKAY"):
        return "approve"
    if word in ("NO", "N", "DENY", "DENIED"):
        return "deny"
    return None


@router.get("/status", response_model=schemas.SmsStatusOut)
def sms_status(user: models.User = Depends(require_parent)):
    enabled = bool(settings.twilio_from_number)
    return schemas.SmsStatusOut(enabled=enabled, phone_number=settings.twilio_from_number or None)


@router.post("/inbound")
def inbound_sms(
    token: str | None = None,
    From: str = Form(...),  # noqa: N803 - matches Twilio's field name exactly
    Body: str = Form(...),  # noqa: N803
    db: Session = Depends(get_db),
):
    # Twilio doesn't sign requests with anything this service can verify
    # without pulling in the `twilio` package purely to check a header --
    # a shared secret in the callback URL is the simplest thing that
    # actually stops a random POST to this public endpoint from creating
    # fake requests or fake approvals. If SMS_WEBHOOK_TOKEN is unset (local
    # dev, or a deployment that hasn't finished Twilio setup) this check is
    # skipped rather than locking the endpoint out entirely.
    if settings.sms_webhook_token and token != settings.sms_webhook_token:
        raise HTTPException(403, "Invalid webhook token")

    try:
        from_number = normalize_phone(From)
    except ValueError:
        return _twiml("Sorry, we couldn't read your number. Please contact your family directly.")

    body_text = (Body or "").strip()

    # --- Case 1: the sender is a registered student, texting to ask for time ---
    student_phone = db.query(models.StudentPhone).filter_by(phone_number=from_number).first()
    if student_phone:
        student = db.get(models.Student, student_phone.student_id)
        if not student:
            return _twiml("Something went wrong finding your profile. Please contact your family directly.")

        restriction = (
            db.query(models.RestrictionEvent)
            .filter_by(student_id=student.id, active=True)
            .order_by(models.RestrictionEvent.started_at.desc())
            .first()
        )
        rule_id = restriction.rule_id if restriction else None
        if not rule_id:
            recent_rule = (
                db.query(models.ScreenTimeRule)
                .filter_by(student_id=student.id, active=True)
                .order_by(models.ScreenTimeRule.created_at.desc())
                .first()
            )
            rule_id = recent_rule.id if recent_rule else None

        req = models.ExtensionRequest(
            student_id=student.id,
            restriction_event_id=restriction.id if restriction else None,
            rule_id=rule_id,
            requested_minutes=_parse_minutes(body_text),
            reason_code="other",
            explanation=f"Requested via text: {body_text[:200]}" if body_text else "Requested via text.",
            status="pending",
        )
        db.add(req)
        db.flush()

        sms_code = create_sms_decision_links(db, family_id=student.family_id, extension_request_id=req.id)
        enqueue_notification(
            db,
            family_id=student.family_id,
            student_id=student.id,
            event_type="extension_requested",
            rule_id=rule_id,
            payload={
                "student_name": student.display_name,
                "requested_minutes": req.requested_minutes,
                "reason_code": "other",
                "explanation": req.explanation,
                "sms_reply_hint": f" Reply YES {sms_code} or NO {sms_code} by text to decide now." if sms_code else "",
            },
        )
        db.commit()
        return _twiml(
            f"Got it, {student.display_name} — we've asked your parent for more time. "
            "We'll text you back as soon as they decide."
        )

    # --- Case 2: the sender is a parent/recipient replying to a pending request ---
    decision = _classify_decision(body_text)
    code_match = re.search(r"\b(\d{3})\b", body_text)
    pending_query = db.query(models.SmsPendingDecision).filter_by(phone_number=from_number, resolved_at=None)
    if code_match:
        pending_query = pending_query.filter_by(code=code_match.group(1))
    pending = pending_query.order_by(models.SmsPendingDecision.created_at.desc()).first()

    if not decision or not pending:
        return _twiml(
            "This number isn't linked to a FocusSentinel student, or there's no pending request to decide. "
            "Reply YES or NO to a specific request, including the code if you have more than one pending."
        )

    req = db.get(models.ExtensionRequest, pending.extension_request_id)
    if not req or req.status != "pending":
        db.query(models.SmsPendingDecision).filter_by(extension_request_id=pending.extension_request_id, resolved_at=None).update(
            {models.SmsPendingDecision.resolved_at: datetime.utcnow()}, synchronize_session=False
        )
        db.commit()
        return _twiml("That request was already decided.")

    student = db.get(models.Student, req.student_id)
    student_name = student.display_name if student else "your student"

    if decision == "approve":
        minutes = req.requested_minutes or DEFAULT_EXTENSION_MINUTES
        approve_request_internal(db, req, user_id=None, actor_type="parent", minutes=minutes)
        reply = f"Approved {minutes} more minutes for {student_name}."
    else:
        deny_request_internal(db, req, user_id=None, actor_type="parent")
        reply = f"Denied the extension request for {student_name}."

    # Any other parent/recipient still linked to this same request no longer
    # has anything to decide -- first reply wins.
    db.query(models.SmsPendingDecision).filter_by(extension_request_id=req.id, resolved_at=None).update(
        {models.SmsPendingDecision.resolved_at: datetime.utcnow()}, synchronize_session=False
    )
    db.commit()
    return _twiml(reply)
