from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time
from enum import Enum
from typing import Optional


class WarningLevel(str, Enum):
    NONE = "none"
    PROGRESS_NOTICE = "progress_notice"   # 80% notice - informational, not a formal warning
    WARNING_ONE = "warning_one"
    WARNING_TWO = "warning_two"
    RESTRICTED = "restricted"


@dataclass
class Rule:
    """Mirrors `screen_time_rules` (database/migrations/0001_init.sql).
    `scope` identifies what this rule applies to; the engine is scope-agnostic
    and just compares elapsed minutes against limits within the allowed window.
    """
    id: str
    name: str
    scope_type: str  # 'category' | 'application' | 'website' | 'device'
    scope_key: str   # e.g. category key, app identifier, domain
    days_of_week: set[int]  # 0=Monday .. 6=Sunday
    daily_limit_minutes: Optional[int]
    warning_one_at_minutes: int
    warning_two_after_additional_minutes: int
    block_after_warning_two_seconds: int
    allowed_start: Optional[time] = None
    allowed_end: Optional[time] = None
    reset_time: time = time(0, 0)
    immediate_enforcement: bool = False
    session_limit_minutes: Optional[int] = None
    is_holiday_exception: bool = False
    active: bool = True

    def applies_on(self, weekday: int) -> bool:
        return weekday in self.days_of_week

    def within_allowed_window(self, current_time: time) -> bool:
        if self.allowed_start is None or self.allowed_end is None:
            return True
        if self.allowed_start <= self.allowed_end:
            return self.allowed_start <= current_time <= self.allowed_end
        # window crosses midnight
        return current_time >= self.allowed_start or current_time <= self.allowed_end


@dataclass
class ExtensionGrant:
    minutes: Optional[int] = None
    until: Optional[time] = None
    rest_of_day: bool = False


@dataclass
class StudentUsageState:
    """Running state for one student + rule scope, held in memory by the API
    per request/session and persisted via warning_events / restriction_events.
    """
    minutes_used_today: float = 0.0
    warning_one_at: Optional[float] = None    # minute-mark warning 1 fired, if it has
    warning_two_at: Optional[float] = None    # minute-mark warning 2 fired, if it has
    restricted_since_minute: Optional[float] = None
    active_extension: Optional[ExtensionGrant] = None
    extension_minutes_granted: float = 0.0

    def effective_limit(self, base_limit: Optional[int]) -> Optional[float]:
        if base_limit is None:
            return None
        return base_limit + self.extension_minutes_granted


@dataclass
class EvaluationResult:
    level: WarningLevel
    minutes_used: float
    limit_minutes: Optional[float]
    minutes_remaining: Optional[float]
    message: str
    seconds_until_restriction: Optional[int] = None
    should_notify: bool = False
