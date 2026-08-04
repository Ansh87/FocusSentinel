from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_device
from ..usage_service import (
    evaluate_and_persist,
    find_active_rule,
    resolve_category_and_website,
    seconds_today_for_rule,
    upsert_daily_total,
)

router = APIRouter(prefix="/usage-events", tags=["usage-events"])

# Minimum active duration counted per sample, to filter out sub-threshold
# false positives (a tab flashed into focus for a fraction of a second,
# transient process spawns, etc.) — see spec section 5.
FALSE_POSITIVE_THRESHOLD_SECONDS = 3


@router.post("/batch", response_model=schemas.UsageEventBatchResponse)
def submit_usage_events(
    payload: schemas.UsageEventBatchRequest,
    db: Session = Depends(get_db),
    device: models.Device = Depends(get_current_device),
):
    student = db.get(models.Student, device.student_id)
    accepted = 0
    duplicates = 0
    totals_by_scope: dict[tuple, dict] = {}

    for event_in in payload.events:
        if event_in.active_duration_seconds < FALSE_POSITIVE_THRESHOLD_SECONDS:
            continue

        category_id, website_id = resolve_category_and_website(db, student.family_id, event_in.identifier)

        row = models.UsageEvent(
            student_id=student.id,
            device_id=device.id,
            website_id=website_id,
            identifier=event_in.identifier,
            category_id=category_id,
            started_at=event_in.started_at,
            ended_at=event_in.ended_at,
            active_duration_seconds=event_in.active_duration_seconds,
            classification_source=event_in.classification_source,
            idempotency_key=event_in.idempotency_key,
        )
        try:
            # A SAVEPOINT (nested transaction) so a duplicate anywhere in the
            # batch only rolls back its own failed insert — not every other
            # event already flushed earlier in this same request/session.
            with db.begin_nested():
                db.add(row)
                db.flush()
        except IntegrityError:
            duplicates += 1
            continue

        accepted += 1
        tz = ZoneInfo(student.timezone or "UTC")
        usage_date = event_in.started_at.astimezone(tz).date().isoformat()
        upsert_daily_total(db, student.id, usage_date, category_id, None, website_id, event_in.active_duration_seconds)

        scope_key = (category_id, website_id)
        totals_by_scope.setdefault(scope_key, {"identifier": event_in.identifier, "seconds": 0, "usage_date": usage_date})
        totals_by_scope[scope_key]["seconds"] += event_in.active_duration_seconds
        totals_by_scope[scope_key]["usage_date"] = usage_date  # most recent event's local day wins

    evaluations = []
    for (category_id, website_id), info in totals_by_scope.items():
        # Use the day's running total (not just this batch) for evaluation,
        # bucketed by the *event's* local calendar day so offline-queued
        # events synced later still land in the correct day's total.
        usage_date = info["usage_date"]
        rule_row = find_active_rule(db, student, category_id, website_id)
        if rule_row is not None:
            # A rule may span several selected websites sharing one daily
            # limit (e.g. TikTok + YouTube Shorts + Instagram Reels), so the
            # figure evaluated against the limit is the *combined* total
            # across everything the rule covers today, not just this one
            # site's total — otherwise splitting time between sites would
            # let a student stay under the limit on paper while blowing
            # past it in aggregate.
            seconds_today = seconds_today_for_rule(db, student.id, usage_date, rule_row)
        else:
            running_total = (
                db.query(models.DailyUsageTotal)
                .filter_by(student_id=student.id, usage_date=usage_date, category_id=category_id, application_id=None, website_id=website_id)
                .first()
            )
            seconds_today = running_total.total_seconds if running_total else info["seconds"]
        result = evaluate_and_persist(db, student, device, info["identifier"], category_id, website_id, seconds_today, usage_date=usage_date)
        evaluations.append(schemas.EvaluationOut(**result))

    db.commit()
    return schemas.UsageEventBatchResponse(accepted=accepted, duplicates=duplicates, evaluations=evaluations)
