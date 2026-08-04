"""API-side notification enqueue helper.

The API's only responsibility is to decide *that* a notification should be
sent and write a durable, deduplicated `notification_events` row. Actually
delivering the notification (email/SMS/push) is the notification-worker
service's job (see services/notification-worker) — this keeps provider
credentials out of the API process entirely and lets the worker be scaled,
retried, or swapped independently.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from . import models
from .phone import normalize_phone

DEDUP_COOLDOWN_MINUTES = 15


def create_sms_decision_links(db: Session, *, family_id: str, extension_request_id: str) -> str | None:
    """Creates one SmsPendingDecision row per SMS-opted-in NotificationRecipient
    in the family, all sharing the same short numeric code, so a parent can
    text "YES 482" / "NO 482" back to approve or deny this specific request
    -- see app/routers/sms.py's inbound webhook. Returns the code, or None
    if nobody in the family has SMS enabled (nothing to link). Doesn't send
    anything itself -- the actual text still goes out through the normal
    enqueue_notification -> notification-worker pipeline; this just makes
    the reply resolvable once it arrives."""
    recipients = (
        db.query(models.NotificationRecipient)
        .filter_by(family_id=family_id)
        .filter(models.NotificationRecipient.mobile_number.isnot(None))
        .all()
    )
    sms_recipients = [r for r in recipients if "sms" in (r.preferred_channels or [])]
    if not sms_recipients:
        return None

    code = f"{random.randint(0, 999):03d}"
    linked_any = False
    for recipient in sms_recipients:
        try:
            normalized = normalize_phone(recipient.mobile_number)
        except ValueError:
            continue
        db.add(
            models.SmsPendingDecision(
                extension_request_id=extension_request_id,
                phone_number=normalized,
                code=code,
            )
        )
        linked_any = True
    if not linked_any:
        return None
    db.flush()
    return code


def enqueue_notification(
    db: Session,
    *,
    family_id: str,
    student_id: str,
    event_type: str,
    rule_id: str | None,
    payload: dict,
) -> list[models.NotificationEvent]:
    recipients = (
        db.query(models.NotificationRecipient)
        .filter_by(family_id=family_id)
        .all()
    )
    created: list[models.NotificationEvent] = []
    cutoff = datetime.utcnow() - timedelta(minutes=DEDUP_COOLDOWN_MINUTES)

    for recipient in recipients:
        if recipient.severity_preference == "restriction_only" and event_type not in (
            "restricted",
            "extension_requested",
            "extension_approved",
            "extension_denied",
        ):
            continue
        if recipient.severity_preference == "daily_summary_only" and event_type not in (
            "daily_summary",
            "weekly_summary",
        ):
            continue

        for channel in recipient.preferred_channels:
            if channel == "email" and not recipient.email:
                continue
            if channel == "sms" and not recipient.mobile_number:
                continue

            dedup_key = f"{event_type}:{student_id}:{rule_id or 'none'}:{recipient.id}:{channel}"
            recent = (
                db.query(models.NotificationEvent)
                .filter(
                    models.NotificationEvent.dedup_key == dedup_key,
                    models.NotificationEvent.created_at >= cutoff,
                    models.NotificationEvent.status != "suppressed_dedup",
                )
                .first()
            )
            status = "suppressed_dedup" if recent else "queued"

            event = models.NotificationEvent(
                family_id=family_id,
                recipient_id=recipient.id,
                event_type=event_type,
                channel=channel,
                dedup_key=dedup_key,
                payload=payload,
                status=status,
            )
            db.add(event)
            created.append(event)

    db.flush()
    return created


def enqueue_direct_email(db: Session, *, to_email: str, event_type: str, payload: dict, dedup_key: str | None = None) -> models.AccountEmailEvent:
    """Queues an email that isn't tied to a family's NotificationRecipient
    list — used for account-level mail like password resets, where the
    recipient is a login email address, not a family contact. Lives in its
    own `account_email_events` table (see the model's docstring) rather than
    `notification_events`, whose `family_id` column is NOT NULL in the
    already-deployed schema. Delivery still depends on a real email_provider
    being configured for notification-worker — the 'console' default just
    logs it, same as every other notification in this app."""
    dedup_key = dedup_key or f"{event_type}:{to_email}"
    cutoff = datetime.utcnow() - timedelta(minutes=DEDUP_COOLDOWN_MINUTES)
    recent = (
        db.query(models.AccountEmailEvent)
        .filter(
            models.AccountEmailEvent.dedup_key == dedup_key,
            models.AccountEmailEvent.created_at >= cutoff,
            models.AccountEmailEvent.status != "suppressed_dedup",
        )
        .first()
    )
    status = "suppressed_dedup" if recent else "queued"
    event = models.AccountEmailEvent(
        to_email=to_email,
        event_type=event_type,
        dedup_key=dedup_key,
        payload=payload,
        status=status,
    )
    db.add(event)
    db.flush()
    return event
