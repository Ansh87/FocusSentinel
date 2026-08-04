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

from sqlalchemy import func
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


def split_identifier(identifier: str) -> tuple[str, str]:
    """The extension (and the fallback catalog classifier) send identifiers
    that are either a bare hostname ("tiktok.com") or a hostname plus a path
    prefix with no separator marker other than the "/" a domain can never
    contain ("youtube.com/shorts"). Splitting on the first "/" recovers both
    parts losslessly."""
    hostname, _, rest = identifier.partition("/")
    path = f"/{rest}" if rest else ""
    return hostname.lower().removeprefix("www."), path


def resolve_category_and_website(db: Session, family_id: str, identifier: str) -> tuple[str | None, str | None]:
    """Returns (category_id, website_id) for a tracked identifier, matching
    against the family's own custom websites plus the global catalog stored
    in the `websites` table. Uses longest-match-wins between a domain-only
    row and a more specific url_pattern row (e.g. youtube.com vs
    youtube.com/shorts), mirroring activity_classifier.classify_domain's
    semantics but against the live, family-extensible table instead of the
    static code catalog — this is what lets a custom "Khan Academy Videos"
    website resolve just as precisely as a built-in one, and is also what
    makes a multi-website rule's individual sites distinguishable from each
    other for combined-usage aggregation (see seconds_today_for_rule)."""
    hostname, path = split_identifier(identifier)

    candidates = (
        db.query(models.Website)
        .filter(
            models.Website.domain == hostname,
            (models.Website.family_id == family_id) | (models.Website.family_id.is_(None)),
        )
        .all()
    )
    best = None
    best_specificity = -1
    for w in candidates:
        if w.url_pattern:
            if not path.startswith(w.url_pattern):
                continue
            specificity = len(w.url_pattern)
        else:
            specificity = 0
        # Longest url_pattern wins; ties (including two domain-only rows)
        # prefer the family's own entry over the shared global catalog one.
        is_family = w.family_id is not None
        if specificity > best_specificity or (specificity == best_specificity and is_family and best is not None and best.family_id is None):
            best, best_specificity = w, specificity
    if best:
        return best.category_id, best.id

    # Fallback to the static code catalog — covers environments where the
    # `websites` table hasn't been seeded yet. Never resolves a website_id
    # here (there's no row to point to), only a category.
    catalog_entry = classify_domain(hostname, path)
    if catalog_entry:
        category = db.query(models.ActivityCategory).filter_by(key=catalog_entry.category).first()
        return (category.id if category else None), None
    return None, None


def find_active_rule(db: Session, student: models.Student, category_id: str | None, website_id: str | None):
    """Most-specific-match-wins rule lookup: a rule whose explicit website
    set includes this exact site outranks a rule merely scoped to the
    site's category, which outranks nothing. This is also what prevents
    double counting — exactly one rule is ever chosen per evaluation."""
    query = db.query(models.ScreenTimeRule).filter_by(student_id=student.id, active=True)
    if website_id:
        rule = (
            query.join(models.RuleWebsite, models.RuleWebsite.rule_id == models.ScreenTimeRule.id)
            .filter(models.RuleWebsite.website_id == website_id)
            .first()
        )
        if rule:
            return rule
        rule = query.filter(models.ScreenTimeRule.scope_website_id == website_id).first()
        if rule:
            return rule
    if category_id:
        rule = query.filter(models.ScreenTimeRule.scope_category_id == category_id).first()
        if rule:
            return rule
    return None


def seconds_today_for_rule(db: Session, student_id: str, usage_date: str, rule: models.ScreenTimeRule) -> int:
    """The combined total across whatever this rule actually covers today —
    every website in its multi-select set, or its whole category, or its
    single legacy scope_website_id — so a limit shared across TikTok +
    YouTube Shorts + Instagram Reels is evaluated against their *sum*, not
    each site's total in isolation."""
    website_ids = [rw.website_id for rw in db.query(models.RuleWebsite).filter_by(rule_id=rule.id).all()]
    if website_ids:
        total = (
            db.query(func.sum(models.DailyUsageTotal.total_seconds))
            .filter(
                models.DailyUsageTotal.student_id == student_id,
                models.DailyUsageTotal.usage_date == usage_date,
                models.DailyUsageTotal.website_id.in_(website_ids),
            )
            .scalar()
        )
        return total or 0
    if rule.scope_website_id:
        total = (
            db.query(func.sum(models.DailyUsageTotal.total_seconds))
            .filter_by(student_id=student_id, usage_date=usage_date, website_id=rule.scope_website_id)
            .scalar()
        )
        return total or 0
    if rule.scope_category_id:
        total = (
            db.query(func.sum(models.DailyUsageTotal.total_seconds))
            .filter_by(student_id=student_id, usage_date=usage_date, category_id=rule.scope_category_id)
            .scalar()
        )
        return total or 0
    return 0


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
