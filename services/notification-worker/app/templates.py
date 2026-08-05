"""Plain-language, non-shaming notification copy. Mirrors the tone rules in
docs/PRD.md — no "wasted time" language, no accusatory framing."""

TEMPLATES = {
    "limit_crossed": (
        "{student_name} reached today's limit",
        "{student_name} has reached today's {rule_name} limit and received a first warning "
        "in FocusSentinel. No action is needed unless the activity continues.",
    ),
    "second_warning": (
        "{student_name}: second warning issued",
        "{student_name} continued past the grace period for {rule_name} and received a second "
        "warning with a short countdown before the activity becomes unavailable.",
    ),
    "restricted": (
        "{student_name}: {rule_name} is now restricted",
        "{rule_name} is now restricted for {student_name} for the rest of today. "
        "They can request more time from their FocusSentinel dashboard.",
    ),
    "extension_requested": (
        "{student_name} requested more time",
        "{student_name} requested {requested_minutes} more minutes ({reason_code}). "
        "Reason given: {explanation}. Review and respond from the FocusSentinel dashboard.",
    ),
    "extension_request_approval": (
        "{student_name} requested more time",
        "{student_name} requested {requested_minutes} more minutes ({reason_code}). "
        "Reason given: {explanation}\n\n"
        "Approve: {approve_url}\n"
        "Deny: {deny_url}\n\n"
        "Or open the FocusSentinel dashboard to decide from there.",
    ),
    "extension_approved": (
        "Extension approved",
        "An extension of {minutes} minutes was approved.",
    ),
    "extension_denied": (
        "Extension request denied",
        "An extension request was denied.",
    ),
    "permission_disabled": (
        "A device permission needs attention",
        "FocusSentinel is missing a permission it needs on one of the family's devices. "
        "Please check the device's settings when convenient.",
    ),
    "device_offline": (
        "A device hasn't checked in recently",
        "FocusSentinel has not received activity information from this device recently. "
        "Please check its permissions or connectivity when convenient.",
    ),
    "password_reset": (
        "Reset your FocusSentinel password",
        "We received a request to reset the password for this account. Use this link within "
        "{expires_minutes} minutes to choose a new one: {reset_url}\n\n"
        "If you didn't request this, you can safely ignore this email.",
    ),
    "daily_summary": (
        "Daily FocusSentinel summary",
        "Here is today's usage summary.",
    ),
    "weekly_summary": (
        "Weekly FocusSentinel summary",
        "Here is this week's usage summary.",
    ),
}


def render(event_type: str, payload: dict) -> tuple[str, str]:
    subject_tpl, body_tpl = TEMPLATES.get(event_type, (event_type, "{message}"))
    safe_payload = {**payload}
    safe_payload.setdefault("student_name", "Your student")
    safe_payload.setdefault("rule_name", "this activity")
    safe_payload.setdefault("message", "")
    safe_payload.setdefault("reset_url", "")
    safe_payload.setdefault("expires_minutes", "")
    safe_payload.setdefault("approve_url", "")
    safe_payload.setdefault("deny_url", "")
    safe_payload.setdefault("requested_minutes", "")
    safe_payload.setdefault("reason_code", "")
    safe_payload.setdefault("explanation", "")
    try:
        subject = subject_tpl.format(**safe_payload)
        body = body_tpl.format(**safe_payload)
    except KeyError:
        subject, body = subject_tpl, payload.get("message", body_tpl)
    return subject, body
