"""SQLAlchemy ORM models mirroring database/migrations/0001_init.sql.

Note: for cross-compatibility with the SQLite test/demo database, JSONB/UUID/
ARRAY Postgres types are represented here with the portable JSON/String
equivalents. The Postgres migration file remains the source of truth for
production schema (types, constraints, indexes); this file targets identical
column semantics.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def gen_id() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)  # parent | student | admin
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    parent_pin_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Family(Base):
    __tablename__ = "families"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    name: Mapped[str] = mapped_column(String, nullable=False)
    timezone: Mapped[str] = mapped_column(String, default="UTC")
    data_retention_days: Mapped[int] = mapped_column(Integer, default=180)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class FamilyMember(Base):
    __tablename__ = "family_members"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    family_id: Mapped[str] = mapped_column(String(36), ForeignKey("families.id"))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    role: Mapped[str] = mapped_column(String, nullable=False)
    __table_args__ = (UniqueConstraint("family_id", "user_id"),)


class Student(Base):
    __tablename__ = "students"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    family_id: Mapped[str] = mapped_column(String(36), ForeignKey("families.id"))
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    age_range: Mapped[str] = mapped_column(String, nullable=False)
    timezone: Mapped[str] = mapped_column(String, default="UTC")
    school_hours: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    bedtime: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Device(Base):
    __tablename__ = "devices"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    student_id: Mapped[str] = mapped_column(String(36), ForeignKey("students.id"))
    device_type: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    platform_identifier: Mapped[str | None] = mapped_column(String, nullable=True)
    device_token_hash: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="active")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DevicePermission(Base):
    __tablename__ = "device_permissions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("devices.id"))
    permission_key: Mapped[str] = mapped_column(String, nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, default=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    __table_args__ = (UniqueConstraint("device_id", "permission_key"),)


class ActivityCategory(Base):
    __tablename__ = "activity_categories"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    key: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    default_classification: Mapped[str] = mapped_column(String, default="neutral")


class Application(Base):
    __tablename__ = "applications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    family_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("families.id"), nullable=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    platform: Mapped[str] = mapped_column(String, nullable=False)
    identifier: Mapped[str] = mapped_column(String, nullable=False)
    category_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("activity_categories.id"), nullable=True)
    classification: Mapped[str] = mapped_column(String, default="neutral")
    source: Mapped[str] = mapped_column(String, default="catalog")


class Website(Base):
    __tablename__ = "websites"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    family_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("families.id"), nullable=True)
    domain: Mapped[str] = mapped_column(String, nullable=False)
    url_pattern: Mapped[str | None] = mapped_column(String, nullable=True)
    label: Mapped[str] = mapped_column(String, nullable=False)
    category_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("activity_categories.id"), nullable=True)
    classification: Mapped[str] = mapped_column(String, default="neutral")
    source: Mapped[str] = mapped_column(String, default="catalog")


class RuleWebsite(Base):
    """Join table letting one rule share a single daily limit across several
    selected websites (e.g. TikTok + YouTube Shorts + Instagram Reels all
    counted together). A brand new table — safe to add via
    `Base.metadata.create_all` without an ALTER TABLE against the already
    deployed `screen_time_rules`/`websites` tables."""

    __tablename__ = "rule_websites"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    rule_id: Mapped[str] = mapped_column(String(36), ForeignKey("screen_time_rules.id"))
    website_id: Mapped[str] = mapped_column(String(36), ForeignKey("websites.id"))
    __table_args__ = (UniqueConstraint("rule_id", "website_id"),)


class ScreenTimeRule(Base):
    __tablename__ = "screen_time_rules"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    family_id: Mapped[str] = mapped_column(String(36), ForeignKey("families.id"))
    student_id: Mapped[str] = mapped_column(String(36), ForeignKey("students.id"))
    name: Mapped[str] = mapped_column(String, nullable=False)
    scope_type: Mapped[str] = mapped_column(String, nullable=False)
    scope_category_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("activity_categories.id"), nullable=True)
    scope_application_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("applications.id"), nullable=True)
    scope_website_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("websites.id"), nullable=True)
    scope_device_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("devices.id"), nullable=True)
    days_of_week: Mapped[list] = mapped_column(JSON, default=lambda: [0, 1, 2, 3, 4, 5, 6])
    allowed_start: Mapped[str | None] = mapped_column(String, nullable=True)  # "HH:MM"
    allowed_end: Mapped[str | None] = mapped_column(String, nullable=True)
    daily_limit_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weekly_limit_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    session_limit_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    warning_one_at_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    warning_two_after_additional_minutes: Mapped[int] = mapped_column(Integer, default=5)
    block_after_warning_two_seconds: Mapped[int] = mapped_column(Integer, default=60)
    reset_time: Mapped[str] = mapped_column(String, default="00:00")
    is_holiday_exception: Mapped[bool] = mapped_column(Boolean, default=False)
    immediate_enforcement: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class UsageEvent(Base):
    __tablename__ = "usage_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    student_id: Mapped[str] = mapped_column(String(36), ForeignKey("students.id"))
    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("devices.id"))
    application_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("applications.id"), nullable=True)
    website_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("websites.id"), nullable=True)
    identifier: Mapped[str] = mapped_column(String, nullable=False)
    category_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("activity_categories.id"), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ended_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    active_duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    rule_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("screen_time_rules.id"), nullable=True)
    classification_source: Mapped[str] = mapped_column(String, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String, nullable=False)
    sync_status: Mapped[str] = mapped_column(String, default="synced")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("device_id", "idempotency_key"),)


class DailyUsageTotal(Base):
    __tablename__ = "daily_usage_totals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    student_id: Mapped[str] = mapped_column(String(36), ForeignKey("students.id"))
    usage_date: Mapped[str] = mapped_column(String, nullable=False)  # "YYYY-MM-DD" local date
    category_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("activity_categories.id"), nullable=True)
    application_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("applications.id"), nullable=True)
    website_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("websites.id"), nullable=True)
    total_seconds: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (
        UniqueConstraint("student_id", "usage_date", "category_id", "application_id", "website_id"),
    )


class WarningEvent(Base):
    __tablename__ = "warning_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    student_id: Mapped[str] = mapped_column(String(36), ForeignKey("students.id"))
    device_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("devices.id"), nullable=True)
    rule_id: Mapped[str] = mapped_column(String(36), ForeignKey("screen_time_rules.id"))
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    minutes_used: Mapped[float] = mapped_column(Float, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    notified: Mapped[bool] = mapped_column(Boolean, default=False)


class RestrictionEvent(Base):
    __tablename__ = "restriction_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    student_id: Mapped[str] = mapped_column(String(36), ForeignKey("students.id"))
    device_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("devices.id"), nullable=True)
    rule_id: Mapped[str] = mapped_column(String(36), ForeignKey("screen_time_rules.id"))
    reason: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    scheduled_reset_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    lifted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lifted_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ExtensionRequest(Base):
    __tablename__ = "extension_requests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    student_id: Mapped[str] = mapped_column(String(36), ForeignKey("students.id"))
    restriction_event_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("restriction_events.id"), nullable=True)
    rule_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("screen_time_rules.id"), nullable=True)
    requested_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requested_until: Mapped[str | None] = mapped_column(String, nullable=True)
    reason_code: Mapped[str] = mapped_column(String, nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, default="pending")
    decided_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    decided_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class NotificationRecipient(Base):
    __tablename__ = "notification_recipients"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    family_id: Mapped[str] = mapped_column(String(36), ForeignKey("families.id"))
    name: Mapped[str] = mapped_column(String, nullable=False)
    relationship: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    mobile_number: Mapped[str | None] = mapped_column(String, nullable=True)
    preferred_channels: Mapped[list] = mapped_column(JSON, default=lambda: ["email"])
    quiet_hours: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    severity_preference: Mapped[str] = mapped_column(String, default="all")
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class NotificationEvent(Base):
    __tablename__ = "notification_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    family_id: Mapped[str] = mapped_column(String(36), ForeignKey("families.id"))
    recipient_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("notification_recipients.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    channel: Mapped[str] = mapped_column(String, nullable=False)
    dedup_key: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String, default="queued")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    family_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("families.id"), nullable=True)
    actor_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    actor_type: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    target_type: Mapped[str | None] = mapped_column(String, nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    event_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DeviceHealthEvent(Base):
    __tablename__ = "device_health_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("devices.id"))
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
