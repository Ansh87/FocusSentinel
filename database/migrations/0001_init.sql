-- FocusSentinel initial schema (canonical reference, Postgres 14+)
-- Run via: psql $DATABASE_URL -f 0001_init.sql
--
-- NOTE on this Phase 1 build: the running API does NOT execute this file.
-- It uses SQLAlchemy's Base.metadata.create_all() against
-- services/api/app/models.py, which intentionally uses portable JSON columns
-- in place of this file's Postgres ARRAY types (e.g. days_of_week,
-- preferred_channels) so the identical ORM models work unchanged against
-- both SQLite (tests/local dev) and Postgres (docker-compose.yml) without a
-- column-type mismatch. Treat this file as the intended production schema
-- and the target for a future Alembic migration, not as something currently
-- applied automatically alongside the ORM.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('parent', 'student', 'admin')),
    display_name TEXT NOT NULL,
    parent_pin_hash TEXT,                 -- only set for parent/guardian users
    email_verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE families (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'UTC',   -- IANA tz, e.g. America/Chicago
    data_retention_days INTEGER NOT NULL DEFAULT 180,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE family_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    family_id UUID NOT NULL REFERENCES families(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('parent', 'student')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (family_id, user_id)
);

CREATE TABLE students (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    family_id UUID NOT NULL REFERENCES families(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL, -- null until student has own login
    display_name TEXT NOT NULL,
    age_range TEXT NOT NULL CHECK (age_range IN ('under_8', '8_12', '13_15', '16_17', '18_plus')),
    timezone TEXT NOT NULL DEFAULT 'UTC',
    school_hours JSONB,        -- {"mon": ["08:00","15:00"], ...}
    bedtime JSONB,             -- {"start": "21:00", "end": "06:30"}
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE devices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    student_id UUID NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    device_type TEXT NOT NULL CHECK (device_type IN ('windows', 'macos', 'android', 'ios', 'browser_extension')),
    name TEXT NOT NULL,
    platform_identifier TEXT,          -- hardware/browser install id
    device_token_hash TEXT NOT NULL,   -- hashed bearer token used by the device
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'revoked', 'pending')),
    last_seen_at TIMESTAMPTZ,
    registered_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE device_permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id UUID NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    permission_key TEXT NOT NULL,     -- e.g. 'usage_access', 'family_controls', 'accessibility'
    granted BOOLEAN NOT NULL DEFAULT false,
    last_checked_at TIMESTAMPTZ,
    UNIQUE (device_id, permission_key)
);

CREATE TABLE activity_categories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key TEXT UNIQUE NOT NULL,   -- 'games','short_form_video','social_media', etc.
    label TEXT NOT NULL,
    default_classification TEXT NOT NULL DEFAULT 'neutral'
        CHECK (default_classification IN ('productive', 'neutral', 'limited'))
);

CREATE TABLE applications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    family_id UUID REFERENCES families(id) ON DELETE CASCADE, -- null = global catalog entry
    name TEXT NOT NULL,
    platform TEXT NOT NULL CHECK (platform IN ('android', 'ios', 'windows', 'macos', 'cross_platform')),
    identifier TEXT NOT NULL,        -- package name / bundle id / executable name
    category_id UUID REFERENCES activity_categories(id),
    classification TEXT NOT NULL DEFAULT 'neutral'
        CHECK (classification IN ('productive', 'neutral', 'limited')),
    source TEXT NOT NULL DEFAULT 'catalog' CHECK (source IN ('catalog', 'manual', 'auto_detected')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE websites (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    family_id UUID REFERENCES families(id) ON DELETE CASCADE, -- null = global catalog entry
    domain TEXT NOT NULL,
    url_pattern TEXT,                -- e.g. '/shorts', 'youtube.com/shorts'
    label TEXT NOT NULL,
    category_id UUID REFERENCES activity_categories(id),
    classification TEXT NOT NULL DEFAULT 'neutral'
        CHECK (classification IN ('productive', 'neutral', 'limited')),
    source TEXT NOT NULL DEFAULT 'catalog' CHECK (source IN ('catalog', 'manual', 'auto_detected')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE classification_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    family_id UUID REFERENCES families(id) ON DELETE CASCADE,
    website_id UUID REFERENCES websites(id) ON DELETE CASCADE,
    application_id UUID REFERENCES applications(id) ON DELETE CASCADE,
    context TEXT NOT NULL DEFAULT 'always' CHECK (context IN ('always', 'school_hours', 'homework', 'weekend', 'bedtime')),
    classification TEXT NOT NULL CHECK (classification IN ('productive', 'neutral', 'limited')),
    CHECK (website_id IS NOT NULL OR application_id IS NOT NULL)
);

CREATE TABLE screen_time_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    family_id UUID NOT NULL REFERENCES families(id) ON DELETE CASCADE,
    student_id UUID NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    scope_type TEXT NOT NULL CHECK (scope_type IN ('category', 'application', 'website', 'device')),
    scope_category_id UUID REFERENCES activity_categories(id),
    scope_application_id UUID REFERENCES applications(id),
    scope_website_id UUID REFERENCES websites(id),
    scope_device_id UUID REFERENCES devices(id),
    days_of_week INTEGER[] NOT NULL DEFAULT '{0,1,2,3,4,5,6}', -- 0=Monday
    allowed_start TIME,
    allowed_end TIME,
    daily_limit_minutes INTEGER,
    weekly_limit_minutes INTEGER,
    session_limit_minutes INTEGER,
    warning_one_at_minutes INTEGER NOT NULL,
    warning_two_after_additional_minutes INTEGER NOT NULL DEFAULT 5,
    block_after_warning_two_seconds INTEGER NOT NULL DEFAULT 60,
    reset_time TIME NOT NULL DEFAULT '00:00',
    is_holiday_exception BOOLEAN NOT NULL DEFAULT false,
    immediate_enforcement BOOLEAN NOT NULL DEFAULT false, -- skip save-grace period if explicitly enabled
    active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE usage_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    student_id UUID NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    device_id UUID NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    application_id UUID REFERENCES applications(id),
    website_id UUID REFERENCES websites(id),
    identifier TEXT NOT NULL,       -- package/bundle/exe/domain actually observed
    category_id UUID REFERENCES activity_categories(id),
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ NOT NULL,
    active_duration_seconds INTEGER NOT NULL CHECK (active_duration_seconds >= 0),
    rule_id UUID REFERENCES screen_time_rules(id),
    classification_source TEXT NOT NULL CHECK (classification_source IN ('catalog', 'manual', 'auto_detected')),
    idempotency_key TEXT NOT NULL,
    sync_status TEXT NOT NULL DEFAULT 'synced' CHECK (sync_status IN ('synced', 'queued_offline')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (device_id, idempotency_key)
);

CREATE INDEX idx_usage_events_student_time ON usage_events (student_id, started_at);

CREATE TABLE daily_usage_totals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    student_id UUID NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    usage_date DATE NOT NULL,           -- in student's local timezone
    category_id UUID REFERENCES activity_categories(id),
    application_id UUID REFERENCES applications(id),
    website_id UUID REFERENCES websites(id),
    total_seconds INTEGER NOT NULL DEFAULT 0,
    UNIQUE (student_id, usage_date, category_id, application_id, website_id)
);

CREATE TABLE warning_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    student_id UUID NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    device_id UUID REFERENCES devices(id),
    rule_id UUID NOT NULL REFERENCES screen_time_rules(id),
    level INTEGER NOT NULL CHECK (level IN (1, 2)),
    minutes_used NUMERIC(6,2) NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    notified BOOLEAN NOT NULL DEFAULT false
);

CREATE TABLE restriction_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    student_id UUID NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    device_id UUID REFERENCES devices(id),
    rule_id UUID NOT NULL REFERENCES screen_time_rules(id),
    reason TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    scheduled_reset_at TIMESTAMPTZ NOT NULL,
    lifted_at TIMESTAMPTZ,
    lifted_reason TEXT CHECK (lifted_reason IN ('scheduled_reset', 'extension_approved', 'parent_pin')),
    active BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE extension_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    student_id UUID NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    restriction_event_id UUID REFERENCES restriction_events(id),
    rule_id UUID REFERENCES screen_time_rules(id),
    requested_minutes INTEGER,
    requested_until TIME,
    reason_code TEXT NOT NULL CHECK (reason_code IN ('friends', 'special_event', 'school_related', 'technical_issue', 'other')),
    explanation TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'denied')),
    decided_by UUID REFERENCES users(id),
    decided_minutes INTEGER,
    decided_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE notification_recipients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    family_id UUID NOT NULL REFERENCES families(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    relationship TEXT NOT NULL,
    email TEXT,
    mobile_number TEXT,
    preferred_channels TEXT[] NOT NULL DEFAULT '{email}', -- subset of {email,sms,push,in_app}
    quiet_hours JSONB,                -- {"start":"21:00","end":"07:00"}
    severity_preference TEXT NOT NULL DEFAULT 'all' CHECK (severity_preference IN ('all', 'restriction_only', 'daily_summary_only')),
    verified BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE notification_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    family_id UUID NOT NULL REFERENCES families(id) ON DELETE CASCADE,
    recipient_id UUID REFERENCES notification_recipients(id),
    event_type TEXT NOT NULL CHECK (event_type IN (
        'limit_crossed', 'second_warning', 'restricted', 'extension_requested',
        'extension_approved', 'extension_denied', 'permission_disabled',
        'device_offline', 'daily_summary', 'weekly_summary'
    )),
    channel TEXT NOT NULL CHECK (channel IN ('email', 'sms', 'push', 'in_app')),
    dedup_key TEXT NOT NULL,          -- used for cooldown/dedup logic
    payload JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'sent', 'failed', 'suppressed_dedup')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_at TIMESTAMPTZ
);

CREATE INDEX idx_notification_events_dedup ON notification_events (dedup_key, created_at);

CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    family_id UUID REFERENCES families(id) ON DELETE CASCADE,
    actor_user_id UUID REFERENCES users(id),
    actor_type TEXT NOT NULL CHECK (actor_type IN ('parent', 'student', 'system')),
    action TEXT NOT NULL,             -- e.g. 'extension_request.approved', 'rule.updated'
    target_type TEXT,
    target_id UUID,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE device_health_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id UUID NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL CHECK (event_type IN (
        'permission_removed', 'extension_disabled', 'service_stopped',
        'clock_changed', 'app_uninstalled', 'disconnected', 'db_reset', 'reconnected'
    )),
    details JSONB,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_device_health_device_time ON device_health_events (device_id, occurred_at);
