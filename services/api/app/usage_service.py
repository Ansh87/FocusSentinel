"""Core usage-evaluation logic: ties incoming usage events to the rules-engine
package, persists warning/restriction state, and enqueues notifications.

Design note on statelessness: the API process holds no in-memory per-student
state between requests (so it can run as multiple replicas). Instead,
StudentUsageState is *reconstructed* on every evaluation from the day's
warning_events/restriction_events rows, then handed to the pure RulesEngine.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from activity_classifier import classify_domain
from rules_engine import ExtensionGrant, Rule, RulesEngine, RealClock, StudentUsageState, WarningLevel

from . import models
from .notifications import enqueue_notification

_engine = RulesEngine(RealClock())


def _parse_time(value: str | None):
    if not value:
        return None
    hh, mm = value.split(":")
    from datetime import time

    return time(int(hh), int(mm))


def _to_domain_rule(row: models.ScreenTimeRule) -> Rule:
    return Rule(
        id=row.id,
        name=row.name,
        scope_type=row.scope_type,
        scope_key=row.scope_category_id or row.scope_application_id or row.scope_website_id or row.scope_device_id or "",
        days_of_week=set(row.days_of_week or []),
        daily_limit_minutes=row.daily_limit_minutes,
        warning_one_at_minutes=row.warning_one_at_minutes,
        warning_two_after_additional_minutes=row.warning_two_after_additional_minutes,
        block_after_warning_two_seconds=row.block_after_warning_two_seconds,
        allowed_start=_parse_time(row.allowed_start),
        allowed_end=_parse_time(row.allowed_end),
        reset_time=_parse_time(row.reset_time) or _parse_time("00:00"),
        immediate_enforcement=row.immediate_enforcement,
        session_limit_minutes=row.session_limit_minutes,
        is_holiday_exception=row.is_holiday_exception,
        active=row.active,
    )


def resolve_category_and_website(db: Session, family_id: str, identifier: str) -> tuple[str | None, str | None]:
    """Returns (category_id, website_id) for a domain identifier, checking the
    family's own website table first, then the global catalog."""
    website = (
        db.query(models.Website)
        .filter(models.Website.family_id == family_id, models.Website.domain == identifier)
        .first()
    )
    if website is None:
        website = (
            db.query(models.Website)
            .filter(models.Website.family_id.is_(None), models.Website.domain == identifier)
            .first()
        )
    if website:
        return website.category_id, website.id

    catalog_entry = classify_domain(identifier)
    if catalog_entry:
        category = db.query(models.ActivityCategory).filter_by(key=catalog_entry.category).first()
        return (category.id if category else None), None
    return None, None


def find_active_rule(db: Session, student: models.Student, category_id: str | None, website_id: str | None):
    query = db.query(models.ScreenTimeRule).filter_by(student_id=student.id, active=True)
    if website_id:
        rule = query.filter(models.ScreenTimeRule.scope_website_id == website_id).first()
        if rule:
            return rule
    if category_id:
        rule = query.filter(models.ScreenTimeRule.scope_category_id == category_id).first()
        if rule:
            return rule
    return None


def _local_today(student: models.Student) -> str:
    tz = ZoneInfo(student.timezone or "UTC")
    return datetime.now(tz).date().isoformat()


def upsert_daily_total(db: Session, student_id: str, usage_date: str, category_id, application_id, website_id, seconds: int):
    row = (
        db.query(models.DailyUsageTotal)
        .filter_by(
            student_id=student_id,
            usage_date=usage_date,
            category_id=category_id,
            application_id=application_id,
            website_id=website_id,
        )
        .first()
    )
    if row is None:
        row = models.DailyUsageTotal(
            student_id=student_id,
            usage_date=usage_date,
            category_id=category_id,
            application_id=application_id,
            website_id=website_id,
            total_seconds=0,
        )
        db.add(row)
    row.total_seconds += seconds
    db.flush()
    return row


def reconstruct_state(db: Session, student_id: str, rule: models.ScreenTimeRule, usage_date: str, tz: str) -> StudentUsageState:
    state = StudentUsageState()

    # `usage_date` is a LOCAL calendar date (e.g. the student's America/Chicago
    # "today"), but WarningEvent/RestrictionEvent/ExtensionRequest timestamps
    # are stored as naive UTC (SQLAlchemy `default=datetime.utcnow`). Naively
    # comparing "2026-08-02" as if it were also a UTC date is wrong by however
    # many hours the timezone is offset — e.g. for America/Chicago, local
    # midnight is 05:00-06:00 UTC, so events from early evening local time
    # (already past UTC midnight) would be silently excluded from "today"'s
    # window, or events from the first few hours of a local day would be
    # incorrectly attributed to the prior UTC date. Converting the local
    # day's start/end into their UTC equivalents before comparing is what
    # makes this correct.
    zone = ZoneInfo(tz)
    local_day_start = datetime.fromisoformat(usage_date).replace(tzinfo=zone)
    day_start = local_day_start.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    day_end = (local_day_start + timedelta(days=1)).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

    w1 = (
        db.query(models.WarningEvent)
        .filter(
            models.WarningEvent.student_id == student_id,
            models.WarningEvent.rule_id == rule.id,
            models.WarningEvent.level == 1,
            models.WarningEvent.occurred_at >= day_start,
            models.WarningEvent.occurred_at < day_end,
        )
        .order_by(models.WarningEvent.occurred_at.asc())
        .first()
    )
    if w1:
        state.warning_one_at = w1.minutes_used

    w2 = (
        db.query(models.WarningEvent)
        .filter(
            models.WarningEvent.student_id == student_id,
            models.WarningEvent.rule_id == rule.id,
            models.WarningEvent.level == 2,
            models.WarningEvent.occurred_at >= day_start,
            models.WarningEvent.occurred_at < day_end,
        )
        .order_by(models.WarningEvent.occurred_at.asc())
        .first()
    )
    if w2:
        state.warning_two_at = w2.minutes_used

    approved = (
        db.query(models.ExtensionRequest)
        .filter(
            models.ExtensionRequest.student_id == student_id,
            models.ExtensionRequest.rule_id == rule.id,
            models.ExtensionRequest.status == "approved",
            models.ExtensionRequest.decided_at >= day_start,
            models.ExtensionRequest.decided_at < day_end,
        )
        .all()
    )
    total_extension = sum((e.decided_minutes or 0) for e in approved)
    if total_extension:
        state.extension_minutes_granted = float(total_extension)
        # An approved extension clears warning state for a fresh cycle, but only
        # if the extension was granted *after* the most recent warning.
        latest_extension_at = max(e.decided_at for e in approved)
        if state.warning_one_at is not None and w1 and latest_extension_at > w1.occurred_at:
            state.warning_one_at = None
            state.warning_two_at = None

    return state


def evaluate_and_persist(db: Session, student: models.Student, device: models.Device, identifier: str, category_id, website_id, seconds_used_total: int, usage_date: str | None = None):
    """Runs one identifier's accumulated today-seconds through the rules
    engine, persisting any new warning/restriction rows and enqueuing
    notifications. Returns an EvaluationResult-like dict.

    `usage_date` should be the *event's* local calendar day (not necessarily
    "now") so that offline-queued events synced after reconnecting are
    evaluated against the day they actually happened on. Defaults to the
    student's current local day when omitted (e.g. for live/online events).
    """
    rule_row = find_active_rule(db, student, category_id, website_id)
    if rule_row is None:
        return {
            "identifier": identifier,
            "level": WarningLevel.NONE.value,
            "message": "Tracked, no limit configured for this activity.",
            "minutes_used": round(seconds_used_total / 60, 2),
            "limit_minutes": None,
            "minutes_remaining": None,
            "seconds_until_restriction": None,
        }

    usage_date = usage_date or _local_today(student)
    state = reconstruct_state(db, student.id, rule_row, usage_date, student.timezone or "UTC")
    rule = _to_domain_rule(rule_row)
    minutes_used = seconds_used_total / 60.0
    had_warning_one = state.warning_one_at is not None
    had_warning_two = state.warning_two_at is not None

    now = datetime.now(ZoneInfo(student.timezone or "UTC"))
    result = _engine.evaluate(rule, state, minutes_used_today=minutes_used, tz=student.timezone or "UTC", now=now)

    # Persist a warning row only the moment the engine *newly* sets the mark
    # (state transitions from unset -> set on this call), not on every
    # subsequent evaluation while still in that warning level. Comparing
    # before/after state avoids brittle float-equality checks against
    # minutes_used, which no longer line up 1:1 once extensions shift the
    # engine's internal (extension-adjusted) bookkeeping.
    if result.level == WarningLevel.WARNING_ONE and not had_warning_one and state.warning_one_at is not None:
        db.add(models.WarningEvent(student_id=student.id, device_id=device.id, rule_id=rule_row.id, level=1, minutes_used=minutes_used, notified=True))
        enqueue_notification(
            db,
            family_id=student.family_id,
            student_id=student.id,
            event_type="limit_crossed",
            rule_id=rule_row.id,
            payload={"rule_name": rule_row.name, "identifier": identifier, "message": result.message},
        )
    elif result.level == WarningLevel.WARNING_TWO and not had_warning_two and state.warning_two_at is not None:
        db.add(models.WarningEvent(student_id=student.id, device_id=device.id, rule_id=rule_row.id, level=2, minutes_used=minutes_used, notified=True))
        enqueue_notification(
            db,
            family_id=student.family_id,
            student_id=student.id,
            event_type="second_warning",
            rule_id=rule_row.id,
            payload={"rule_name": rule_row.name, "identifier": identifier, "message": result.message},
        )
    elif result.level == WarningLevel.RESTRICTED:
        existing = (
            db.query(models.RestrictionEvent)
            .filter_by(student_id=student.id, rule_id=rule_row.id, active=True)
            .first()
        )
        if existing is None:
            reset_dt = datetime.combine(datetime.fromisoformat(usage_date).date() + timedelta(days=1), rule.reset_time)
            db.add(
                models.RestrictionEvent(
                    student_id=student.id,
                    device_id=device.id,
                    rule_id=rule_row.id,
                    reason=result.message,
                    scheduled_reset_at=reset_dt,
                )
            )
            enqueue_notification(
                db,
                family_id=student.family_id,
                student_id=student.id,
                event_type="restricted",
                rule_id=rule_row.id,
                payload={"rule_name": rule_row.name, "identifier": identifier, "message": result.message},
            )

    db.flush()
    return {
        "identifier": identifier,
        "level": result.level.value,
        "message": result.message,
        "minutes_used": round(result.minutes_used, 2),
        "limit_minutes": result.limit_minutes,
        "minutes_remaining": result.minutes_remaining,
        "seconds_until_restriction": result.seconds_until_restriction,
    }
