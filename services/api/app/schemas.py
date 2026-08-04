from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field


# ---- Auth ----
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    display_name: str
    role: Literal["parent", "student"] = "parent"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    role: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class RequestPasswordResetRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8)


class StudentLoginCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class StudentLoginStatus(BaseModel):
    has_login: bool
    email: Optional[str] = None


# ---- Families / Students ----
class FamilyCreate(BaseModel):
    name: str
    timezone: str = "UTC"


class FamilyUpdate(BaseModel):
    name: Optional[str] = None
    timezone: Optional[str] = None


class FamilyOut(BaseModel):
    id: str
    name: str
    timezone: str
    model_config = {"from_attributes": True}


class SetupStatusOut(BaseModel):
    family_id: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    family_profile_completed: bool
    student_added: bool
    first_rule_created: bool
    device_connected: bool
    device_connect_skipped: bool
    completed_steps: int
    total_steps: int
    is_complete: bool
    remaining_steps: list[str]
    reminder_dismissed_until: Optional[datetime] = None


class StudentCreate(BaseModel):
    family_id: str
    display_name: str
    age_range: Literal["under_8", "8_12", "13_15", "16_17", "18_plus"]
    timezone: str = "UTC"


class StudentUpdate(BaseModel):
    display_name: Optional[str] = None
    age_range: Optional[Literal["under_8", "8_12", "13_15", "16_17", "18_plus"]] = None
    timezone: Optional[str] = None


class StudentOut(BaseModel):
    id: str
    family_id: str
    display_name: str
    age_range: str
    timezone: str
    is_sibling_manager: bool = False
    sibling_manager_until: Optional[datetime] = None
    is_archived: bool = False
    model_config = {"from_attributes": True}


class SiblingManagerGrantRequest(BaseModel):
    # Hours until this grant expires; omit or null for an indefinite grant
    # (until a parent manually revokes it).
    hours: Optional[int] = Field(default=None, gt=0, le=8760)


class SiblingManagerStatus(BaseModel):
    student_id: str
    is_sibling_manager: bool
    expires_at: Optional[datetime] = None


class UserOut(BaseModel):
    id: str
    email: str
    display_name: str
    role: str
    model_config = {"from_attributes": True}


# ---- Devices ----
class DeviceRegisterRequest(BaseModel):
    student_id: str
    device_type: Literal["windows", "macos", "android", "ios", "browser_extension"]
    name: str
    platform_identifier: Optional[str] = None


class DeviceRegisterResponse(BaseModel):
    device_id: str
    device_token: str  # plaintext, shown once


class DeviceHeartbeat(BaseModel):
    permissions: dict[str, bool] = {}


# ---- Websites ----
class WebsiteOut(BaseModel):
    id: str
    domain: str
    url_pattern: Optional[str] = None
    label: str
    category_id: Optional[str] = None
    source: str
    is_custom: bool = False
    model_config = {"from_attributes": True}


class WebsiteCreate(BaseModel):
    family_id: str
    domain: str
    label: str
    url_pattern: Optional[str] = None
    category_key: Optional[str] = None


# ---- Rules ----
class RuleCreate(BaseModel):
    student_id: str
    name: str
    scope_type: Literal["category", "application", "website", "device"]
    scope_category_key: Optional[str] = None
    scope_application_id: Optional[str] = None
    scope_website_id: Optional[str] = None
    scope_device_id: Optional[str] = None
    website_ids: list[str] = Field(default_factory=list)
    days_of_week: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4, 5, 6])
    allowed_start: Optional[str] = None  # "HH:MM"
    allowed_end: Optional[str] = None
    daily_limit_minutes: Optional[int] = None
    warning_one_at_minutes: int
    warning_two_after_additional_minutes: int = 5
    block_after_warning_two_seconds: int = 60
    reset_time: str = "00:00"
    immediate_enforcement: bool = False


class RuleUpdate(BaseModel):
    name: Optional[str] = None
    student_id: Optional[str] = None
    scope_category_key: Optional[str] = None
    website_ids: Optional[list[str]] = None
    days_of_week: Optional[list[int]] = None
    allowed_start: Optional[str] = None
    allowed_end: Optional[str] = None
    daily_limit_minutes: Optional[int] = None
    warning_one_at_minutes: Optional[int] = None
    warning_two_after_additional_minutes: Optional[int] = None
    block_after_warning_two_seconds: Optional[int] = None
    reset_time: Optional[str] = None
    active: Optional[bool] = None


class RuleOut(BaseModel):
    id: str
    student_id: str
    name: str
    scope_type: str
    scope_category_key: Optional[str] = None
    websites: list[WebsiteOut] = Field(default_factory=list)
    daily_limit_minutes: Optional[int]
    warning_one_at_minutes: int
    warning_two_after_additional_minutes: Optional[int] = None
    block_after_warning_two_seconds: Optional[int] = None
    days_of_week: Optional[list[int]] = None
    reset_time: Optional[str] = None
    active: bool
    model_config = {"from_attributes": True}


# ---- Usage events ----
class UsageEventIn(BaseModel):
    identifier: str  # domain, package, process, bundle id
    category_key: Optional[str] = None
    started_at: datetime
    ended_at: datetime
    active_duration_seconds: int
    classification_source: Literal["catalog", "manual", "auto_detected"] = "catalog"
    idempotency_key: str


class UsageEventBatchRequest(BaseModel):
    device_id: str
    events: list[UsageEventIn]


class EvaluationOut(BaseModel):
    identifier: str
    level: str
    message: str
    minutes_used: float
    limit_minutes: Optional[float]
    minutes_remaining: Optional[float]
    seconds_until_restriction: Optional[int] = None


class UsageEventBatchResponse(BaseModel):
    accepted: int
    duplicates: int
    evaluations: list[EvaluationOut]


class TodayUsageOut(BaseModel):
    student_id: str
    date: str
    total_seconds_by_category: dict[str, int]
    total_seconds_by_rule: dict[str, int] = Field(default_factory=dict)
    active_warnings: list[dict]
    active_restrictions: list[dict]


class UsageHistoryDay(BaseModel):
    date: str
    total_seconds: int
    total_seconds_by_category: dict[str, int]


class UsageHistoryOut(BaseModel):
    student_id: str
    days: list[UsageHistoryDay]


# ---- Extension requests ----
class ExtensionRequestCreate(BaseModel):
    student_id: str
    restriction_event_id: Optional[str] = None
    rule_id: Optional[str] = None
    requested_minutes: Optional[int] = None
    reason_code: Literal["friends", "special_event", "school_related", "technical_issue", "other"]
    explanation: Optional[str] = None


class ExtensionRequestOut(BaseModel):
    id: str
    student_id: str
    rule_id: Optional[str] = None
    requested_minutes: Optional[int]
    reason_code: str
    explanation: Optional[str] = None
    status: str
    created_at: datetime
    model_config = {"from_attributes": True}


class ExtensionDecision(BaseModel):
    minutes: Optional[int] = None
    rest_of_day: bool = False


class ExtensionGrantRequest(BaseModel):
    student_id: str
    rule_id: str
    minutes: int = Field(gt=0)


# ---- Notification recipients ----
class NotificationRecipientCreate(BaseModel):
    family_id: str
    name: str
    relationship: str
    email: Optional[EmailStr] = None
    mobile_number: Optional[str] = None
    preferred_channels: list[str] = Field(default_factory=lambda: ["email"])
    severity_preference: Literal["all", "restriction_only", "daily_summary_only"] = "all"


class NotificationRecipientOut(BaseModel):
    id: str
    name: str
    relationship: str
    email: Optional[str]
    verified: bool
    model_config = {"from_attributes": True}


class AuditLogOut(BaseModel):
    id: str
    actor_type: str
    action: str
    target_type: Optional[str]
    created_at: datetime
    model_config = {"from_attributes": True}


class DeviceHealthOut(BaseModel):
    device_id: str
    device_name: str
    status: str
    platform_identifier: Optional[str] = None
    last_seen_at: Optional[datetime]
    permissions: dict[str, bool]
