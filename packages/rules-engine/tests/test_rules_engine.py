from datetime import datetime, time
from zoneinfo import ZoneInfo

import pytest

from rules_engine import (
    ExtensionGrant,
    Rule,
    RulesEngine,
    SimulatedClock,
    StudentUsageState,
    WarningLevel,
)


def make_rule(**overrides) -> Rule:
    defaults = dict(
        id="rule-1",
        name="Weekday gaming limit",
        scope_type="category",
        scope_key="games",
        days_of_week={0, 1, 2, 3, 4},  # Mon-Fri
        daily_limit_minutes=45,
        warning_one_at_minutes=45,
        warning_two_after_additional_minutes=5,
        block_after_warning_two_seconds=60,
        allowed_start=time(16, 0),
        allowed_end=time(20, 30),
    )
    defaults.update(overrides)
    return Rule(**defaults)


@pytest.fixture
def monday_4pm():
    # 2026-08-03 is a Monday
    return datetime(2026, 8, 3, 16, 0, tzinfo=ZoneInfo("America/Chicago"))


def test_progress_notice_at_80_percent(monday_4pm):
    clock = SimulatedClock(monday_4pm)
    engine = RulesEngine(clock)
    rule = make_rule()
    state = StudentUsageState()

    result = engine.evaluate(rule, state, minutes_used_today=36, tz="America/Chicago", now=monday_4pm)

    assert result.level == WarningLevel.PROGRESS_NOTICE
    assert "remaining" in result.message
    assert result.should_notify is False


def test_warning_one_fires_at_limit_and_notifies(monday_4pm):
    clock = SimulatedClock(monday_4pm)
    engine = RulesEngine(clock)
    rule = make_rule()
    state = StudentUsageState()

    result = engine.evaluate(rule, state, minutes_used_today=45, tz="America/Chicago", now=monday_4pm)

    assert result.level == WarningLevel.WARNING_ONE
    assert result.should_notify is True
    assert "45-minute" in result.message
    assert state.warning_one_at == 45


def test_warning_two_fires_after_grace_minutes(monday_4pm):
    clock = SimulatedClock(monday_4pm)
    engine = RulesEngine(clock)
    rule = make_rule()
    state = StudentUsageState()

    engine.evaluate(rule, state, minutes_used_today=45, tz="America/Chicago", now=monday_4pm)
    result = engine.evaluate(rule, state, minutes_used_today=50, tz="America/Chicago", now=monday_4pm)

    assert result.level == WarningLevel.WARNING_TWO
    assert result.seconds_until_restriction == 60
    assert state.warning_two_at == 50


def test_restriction_after_countdown_elapses(monday_4pm):
    """A 45-minute limit's full warning->restriction sequence, exercised in
    milliseconds via SimulatedClock instead of real sleeps."""
    clock = SimulatedClock(monday_4pm)
    engine = RulesEngine(clock)
    rule = make_rule()
    state = StudentUsageState()

    engine.evaluate(rule, state, minutes_used_today=45, tz="America/Chicago", now=monday_4pm)  # W1
    engine.evaluate(rule, state, minutes_used_today=50, tz="America/Chicago", now=monday_4pm)  # W2

    # 61 seconds later, still at minute 50 usage-wise but wall clock advanced past grace window.
    # We simulate this the same way the API does: minutes_used_today creeps up slightly
    # as the (still-active, unrestricted-until-now) session continues.
    clock.advance(seconds=61)
    result = engine.evaluate(
        rule, state, minutes_used_today=50 + 61 / 60, tz="America/Chicago", now=clock.now("America/Chicago")
    )

    assert result.level == WarningLevel.RESTRICTED
    assert result.should_notify is True
    assert result.minutes_remaining == 0


def test_extension_grant_clears_warnings_and_raises_limit(monday_4pm):
    clock = SimulatedClock(monday_4pm)
    engine = RulesEngine(clock)
    rule = make_rule()
    state = StudentUsageState()

    engine.evaluate(rule, state, minutes_used_today=45, tz="America/Chicago", now=monday_4pm)
    engine.evaluate(rule, state, minutes_used_today=50, tz="America/Chicago", now=monday_4pm)
    assert state.warning_two_at is not None

    RulesEngine.apply_extension(state, ExtensionGrant(minutes=15), minutes=15)
    assert state.warning_one_at is None
    assert state.warning_two_at is None

    result = engine.evaluate(rule, state, minutes_used_today=50, tz="America/Chicago", now=monday_4pm)
    assert result.level in (WarningLevel.NONE, WarningLevel.PROGRESS_NOTICE)
    assert result.limit_minutes == 60  # 45 base + 15 extension


def test_rule_does_not_apply_on_weekend(monday_4pm):
    saturday = monday_4pm.replace(day=8)  # 2026-08-08 is a Saturday
    clock = SimulatedClock(saturday)
    engine = RulesEngine(clock)
    rule = make_rule()  # Mon-Fri only
    state = StudentUsageState()

    result = engine.evaluate(rule, state, minutes_used_today=200, tz="America/Chicago", now=saturday)
    assert result.level == WarningLevel.NONE


def test_outside_allowed_window_is_restricted(monday_4pm):
    early_morning = monday_4pm.replace(hour=7, minute=0)
    clock = SimulatedClock(early_morning)
    engine = RulesEngine(clock)
    rule = make_rule()  # allowed 16:00-20:30
    state = StudentUsageState()

    result = engine.evaluate(rule, state, minutes_used_today=0, tz="America/Chicago", now=early_morning)
    assert result.level == WarningLevel.RESTRICTED


def test_cross_midnight_session_uses_per_calendar_day_totals():
    """Usage accrued before midnight and after midnight must be attributed to
    two different local calendar days; the engine itself is stateless per call,
    so this test asserts the *caller's* responsibility (splitting at local
    midnight) produces two independent evaluations rather than one combined one."""
    before_midnight = datetime(2026, 8, 3, 23, 50, tzinfo=ZoneInfo("America/Chicago"))
    after_midnight = datetime(2026, 8, 4, 0, 10, tzinfo=ZoneInfo("America/Chicago"))
    clock = SimulatedClock(before_midnight)
    engine = RulesEngine(clock)
    rule = make_rule(allowed_start=None, allowed_end=None, days_of_week=set(range(7)))

    state_day1 = StudentUsageState()
    result_day1 = engine.evaluate(rule, state_day1, minutes_used_today=40, tz="America/Chicago", now=before_midnight)
    assert result_day1.level == WarningLevel.PROGRESS_NOTICE

    # New calendar day -> fresh state, usage resets to reflect only the new day's minutes
    state_day2 = StudentUsageState()
    result_day2 = engine.evaluate(rule, state_day2, minutes_used_today=10, tz="America/Chicago", now=after_midnight)
    assert result_day2.level == WarningLevel.NONE


def test_dst_transition_does_not_break_window_check():
    """US DST spring-forward 2027-03-14: 2:00 AM -> 3:00 AM. A rule window that
    spans the transition should still evaluate using local wall-clock time.

    2027-03-14 is a Sunday (that's why it's the DST date - the US rule is the
    second Sunday in March), so the rule's days_of_week has to include Sunday
    or this test would just be exercising the day-of-week check instead of
    the DST/window logic it's meant to cover.
    """
    dst_day = datetime(2027, 3, 14, 16, 0, tzinfo=ZoneInfo("America/Chicago"))
    clock = SimulatedClock(dst_day)
    engine = RulesEngine(clock)
    rule = make_rule(days_of_week=set(range(7)))
    state = StudentUsageState()

    result = engine.evaluate(rule, state, minutes_used_today=10, tz="America/Chicago", now=dst_day)
    assert result.level == WarningLevel.NONE
    assert result.minutes_remaining == 35
