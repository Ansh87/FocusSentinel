"""API-side notification enqueue helper.

The API's only responsibility is to decide *that* a notification should be
sent and write a durable, deduplicated `notification_events` row. Actually
delivering the notification (email/SMS/push) is the notification-worker
service's job (see services/notification-worker) — this keeps provider
credentials out of the API process entirely and lets the worker be scaled,
retried, or swapped independently.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from . import models

DEDUP_COOLDOWN_MINUTES = 15


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
