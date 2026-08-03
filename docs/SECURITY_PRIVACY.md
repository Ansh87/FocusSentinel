# FocusSentinel — Security & Privacy

FocusSentinel is built to the principle that a family safety tool must never itself become a surveillance risk. This document describes what is implemented today (Phase 1) and what a production rollout still needs.

## Data minimization

`usage_events` (see `database/migrations/0001_init.sql`) stores exactly: student ID, device ID, the identifier actually observed (domain/package/process/bundle ID), category, start/end timestamps, active duration, the rule applied, classification source, and sync status. It never stores page content, message content, search queries, screenshots, keystrokes, form entries, camera/microphone data, or private files. There is no code path anywhere in this repo that captures any of those things — this is a structural property of the schema and the ingestion endpoint (`POST /usage-events/batch`), not a policy promise layered on top.

## Authentication and authorization

- Parent/student/admin accounts authenticate with email + password (bcrypt via `passlib`) and receive short-lived JWT access tokens plus longer-lived refresh tokens (`services/api/app/security.py`).
- Devices (browser extension, future native agents) authenticate with a **separate, narrowly scoped bearer token** generated at registration (`POST /devices/register`) and stored server-side only as a SHA-256 hash — the plaintext is shown once and never persisted. A compromised device token can submit usage events for its own student and nothing else; it cannot read dashboard data, create rules, or act as any user.
- Role-based access control gates parent-only actions (`services/api/app/deps.py::require_parent`) — rule changes, extension approvals, device registration, recipient management, and audit log access all require a parent/guardian or admin role.
- A parent PIN field exists on the `users` table (`parent_pin_hash`) for local device-side unlock flows (e.g., the browser restriction page's "I'm a parent" button); wiring a PIN-entry UI to it is a near-term follow-up, not yet built in this pass.

## Transport and storage

- All API traffic is intended to run behind HTTPS/TLS in any real deployment (`docker-compose.yml` and the Dockerfiles here are for local development; a production deployment should terminate TLS at a reverse proxy or load balancer in front of the `api` and `web-dashboard` services).
- Passwords and device tokens are hashed before storage; nothing else in the schema is currently marked for column-level encryption because nothing else in the schema is sensitive in that way (no content, no messages, no location).

## Rate limiting, dedup, and abuse prevention

- Notification dedup/cooldown is implemented (`services/api/app/notifications.py`): the same event type + student + rule + recipient + channel combination is suppressed for 15 minutes, preventing repeat-warning spam.
- Usage-event ingestion is idempotent via a per-device unique `idempotency_key`, so retried/duplicated batches (a normal consequence of offline sync) cannot inflate usage totals or re-trigger warnings.
- API-wide rate limiting (e.g., per-IP or per-token request throttling) is **not yet implemented** in this pass — see `docs/KNOWN_LIMITATIONS.md`.

## Audit logging

Every rule change, device registration/revocation, and extension approval/denial writes an `audit_logs` row with the acting user, action, target, and metadata (`services/api/app/routers/*.py`). This is queryable via `GET /audit-log`.

## Device revocation and permission health

Parents can revoke a device (`POST /devices/{id}/revoke`), immediately invalidating its token. Device permission changes (e.g., a permission that was granted becoming un-granted) are recorded as `device_health_events` and surfaced with neutral, non-accusatory language ("FocusSentinel has not received activity information from this device since...") rather than assuming bad intent — see `services/api/app/routers/device_health.py`.

## What FocusSentinel will never do

Per the product's non-negotiable design principles: it will not hide from the device owner, record the screen, capture keystrokes, read private messages, access photos/files without a direct feature need, activate the microphone or camera, track physical location, sell activity data, use student activity for advertising, or claim regulatory compliance (COPPA, FERPA, etc.) without a real legal review — none of which has happened for this codebase. Anyone deploying FocusSentinel for a school or in a jurisdiction with specific student-data-privacy law should get that legal review before launch; nothing in this document is legal advice.

## Gaps to close before a real deployment

1. Recipient email/phone verification flow (the field exists; the confirmation-code flow does not).
2. API rate limiting.
3. Refresh-token rotation/revocation list (tokens are currently stateless JWTs with an expiry, not yet tracked for individual revocation).
4. Parent-PIN entry UI wired to the existing `parent_pin_hash` field.
5. Configurable data-retention enforcement (the `families.data_retention_days` column exists; a scheduled purge job does not yet exist).
6. TLS termination and secrets management for a real deployment target (this repo ships env-var-based config suitable for a secrets manager, but doesn't include one).
