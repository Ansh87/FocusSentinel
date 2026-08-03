from __future__ import annotations

from datetime import datetime

from .clock import Clock
from .models import EvaluationResult, ExtensionGrant, Rule, StudentUsageState, WarningLevel


class RulesEngine:
    """Pure, deterministic evaluation of a student's usage against one rule.

    The engine never reads a clock itself for elapsed-time math; the caller
    (API layer) supplies `minutes_used_today` computed from usage_events, and
    `now` for window/day-of-week checks and grace-period countdowns. This
    keeps the engine trivially testable with SimulatedClock and avoids any
    reliance on wall-clock sleeps in tests.
    """

    def __init__(self, clock: Clock):
        self._clock = clock

    def evaluate(
        self,
        rule: Rule,
        state: StudentUsageState,
        minutes_used_today: float,
        tz: str,
        now: datetime | None = None,
    ) -> EvaluationResult:
        now = now or self._clock.now(tz)
        weekday = now.weekday()
        state.minutes_used_today = minutes_used_today

        if not rule.active or not rule.applies_on(weekday) or rule.is_holiday_exception:
            return EvaluationResult(
                level=WarningLevel.NONE,
                minutes_used=minutes_used_today,
                limit_minutes=None,
                minutes_remaining=None,
                message="No limit applies right now.",
            )

        if not rule.within_allowed_window(now.time()):
            return EvaluationResult(
                level=WarningLevel.RESTRICTED,
                minutes_used=minutes_used_today,
                limit_minutes=0,
                minutes_remaining=0,
                message=f"{rule.name} is only available between "
                        f"{rule.allowed_start} and {rule.allowed_end}.",
            )

        limit = state.effective_limit(rule.daily_limit_minutes)
        if limit is None:
            return EvaluationResult(
                level=WarningLevel.NONE,
                minutes_used=minutes_used_today,
                limit_minutes=None,
                minutes_remaining=None,
                message="Tracked, no daily limit configured.",
            )

        remaining = max(limit - minutes_used_today, 0.0)
        warning_two_threshold = rule.warning_one_at_minutes + rule.warning_two_after_additional_minutes

        # Approved extensions shift the warning thresholds forward by the
        # granted amount (rather than resetting minutes_used_today), so a
        # student who used 50 of 45+15=60 minutes sees fresh warning zones
        # relative to the *new* limit instead of instantly re-tripping
        # warning two the moment the next event is evaluated.
        adjusted_minutes = minutes_used_today - state.extension_minutes_granted

        # --- Restricted: already past warning two and grace countdown elapsed ---
        if state.warning_two_at is not None:
            seconds_since_w2 = (adjusted_minutes - state.warning_two_at) * 60
            if seconds_since_w2 >= rule.block_after_warning_two_seconds:
                return EvaluationResult(
                    level=WarningLevel.RESTRICTED,
                    minutes_used=minutes_used_today,
                    limit_minutes=limit,
                    minutes_remaining=0,
                    message=f"{rule.name} is restricted for today. "
                            f"It will be available again at {rule.reset_time}.",
                    should_notify=True,
                )
            seconds_left = max(rule.block_after_warning_two_seconds - seconds_since_w2, 0)
            return EvaluationResult(
                level=WarningLevel.WARNING_TWO,
                minutes_used=minutes_used_today,
                limit_minutes=limit,
                minutes_remaining=0,
                seconds_until_restriction=int(seconds_left),
                message=f"Second warning: this will be unavailable in "
                        f"{int(seconds_left)} seconds. Save your progress now.",
            )

        # --- Warning two: past warning-one threshold + grace minutes ---
        if adjusted_minutes >= warning_two_threshold:
            if state.warning_two_at is None:
                state.warning_two_at = adjusted_minutes
            return EvaluationResult(
                level=WarningLevel.WARNING_TWO,
                minutes_used=minutes_used_today,
                limit_minutes=limit,
                minutes_remaining=0,
                seconds_until_restriction=rule.block_after_warning_two_seconds,
                message=f"Second warning: this will be unavailable in "
                        f"{rule.block_after_warning_two_seconds} seconds. Save your progress now.",
                should_notify=True,
            )

        # --- Warning one: at/over the configured limit ---
        if adjusted_minutes >= rule.warning_one_at_minutes:
            if state.warning_one_at is None:
                state.warning_one_at = adjusted_minutes
            extra = rule.warning_two_after_additional_minutes
            return EvaluationResult(
                level=WarningLevel.WARNING_ONE,
                minutes_used=minutes_used_today,
                limit_minutes=limit,
                minutes_remaining=0,
                message=f"You have reached today's {int(rule.warning_one_at_minutes)}-minute "
                        f"limit for {rule.name}. Please save your progress and exit. "
                        f"You have {extra} additional minutes before the second warning.",
                should_notify=True,
            )

        # --- Progress notice at 80% (informational, not a formal warning) ---
        if limit > 0 and adjusted_minutes >= 0.8 * rule.warning_one_at_minutes:
            return EvaluationResult(
                level=WarningLevel.PROGRESS_NOTICE,
                minutes_used=minutes_used_today,
                limit_minutes=limit,
                minutes_remaining=remaining,
                message=f"You have {round(remaining)} minutes remaining for {rule.name} today.",
            )

        return EvaluationResult(
            level=WarningLevel.NONE,
            minutes_used=minutes_used_today,
            limit_minutes=limit,
            minutes_remaining=remaining,
            message=f"{round(remaining)} minutes remaining today.",
        )

    @staticmethod
    def apply_extension(state: StudentUsageState, grant: ExtensionGrant, minutes: float) -> None:
        """Applies an approved extension request, clearing warning state so the
        student gets a fresh warning-one/warning-two cycle for the extended time,
        and lifting any active restriction.
        """
        state.active_extension = grant
        state.extension_minutes_granted += minutes
        state.warning_one_at = None
        state.warning_two_at = None
        state.restricted_since_minute = None
