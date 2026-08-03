# FocusSentinel — Architecture

## System diagram

```mermaid
flowchart TB
    subgraph Clients
        WEB[Web Dashboard<br/>Next.js]
        EXT[Chrome/Edge Extension<br/>Manifest V3]
        WIN[Windows Agent<br/>.NET Worker - Phase 2 scaffold]
        AND[Android App<br/>Kotlin - Phase 3 scaffold]
        IOS[iOS App<br/>Swift/SwiftUI - Phase 4 scaffold]
        MAC[macOS Agent<br/>Swift - Phase 5]
    end

    subgraph Backend
        API[FastAPI Service]
        RULES[rules-engine package]
        CLASSIFIER[activity-classifier package]
        WORKER[Notification Worker<br/>Celery + Redis]
    end

    subgraph Data
        PG[(PostgreSQL)]
        REDIS[(Redis - queue/broker)]
    end

    subgraph Providers
        SMTP[Email provider<br/>SMTP/SendGrid/SES/Resend]
        SMS[SMS provider<br/>Twilio-compatible]
        PUSH[Push provider<br/>FCM/APNs]
    end

    WEB -->|HTTPS/JWT| API
    EXT -->|HTTPS/device token| API
    WIN -.->|planned| API
    AND -.->|planned| API
    IOS -.->|planned| API
    MAC -.->|planned| API

    API --> RULES
    API --> CLASSIFIER
    API --> PG
    API --> REDIS
    WORKER --> REDIS
    WORKER --> PG
    WORKER --> SMTP
    WORKER --> SMS
    WORKER --> PUSH
```

## Data flow — warning/restriction sequence

```mermaid
sequenceDiagram
    participant Ext as Browser Extension
    participant API as FastAPI
    participant DB as PostgreSQL
    participant Worker as Notification Worker
    participant Parent as Parent (email/SMS/dashboard)

    Ext->>API: POST /usage-events/batch (active-time samples)
    API->>DB: upsert usage_events, recompute daily_usage_totals
    API->>API: rules-engine.evaluate(student, category)
    alt 80% of limit
        API-->>Ext: progress notice (non-punitive)
    else 100% of limit (Warning 1)
        API->>DB: insert warning_events (level=1)
        API->>Worker: enqueue notification (limit_reached)
        Worker->>Parent: email/SMS/push
        API-->>Ext: show Warning 1 UI
    else grace period elapsed (Warning 2)
        API->>DB: insert warning_events (level=2)
        API-->>Ext: show Warning 2 UI + countdown
    else countdown elapsed
        API->>DB: insert restriction_events
        API->>Worker: enqueue notification (restricted)
        Worker->>Parent: email/SMS/push
        API-->>Ext: apply declarativeNetRequest block, show restriction page
    end
    Note over Ext,API: Student requests extension
    Ext->>API: POST /extension-requests
    API->>Worker: enqueue notification (extension_requested)
    Parent->>API: POST /extension-requests/{id}/approve
    API->>DB: insert audit_logs, update restriction window
    API-->>Ext: restriction lifted for approved duration
```

## Monorepo layout

```text
focussentinel/
  apps/
    web-dashboard/        # Next.js (implemented)
    browser-extension/    # Manifest V3 (implemented)
    android/              # Phase 3 scaffold + docs only
    ios/                  # Phase 4 scaffold + docs only
    windows-agent/        # Phase 2 scaffold + docs only
    macos-agent/          # Phase 5 scaffold + docs only
  services/
    api/                   # FastAPI (implemented)
    notification-worker/   # Celery worker (implemented)
  packages/
    shared-types/          # TS types shared by web + extension
    rules-engine/          # Python rules engine + simulated clock (implemented)
    activity-classifier/   # domain/app classification catalog (implemented)
  database/
    migrations/            # raw SQL migrations
    seed/                  # demo family/student/rules
  docs/
```

## Key architectural decisions

- **Rules engine is a standalone package**, not inline API logic, so it can be unit tested with a simulated clock (45-minute limits tested in seconds) and reused by future native agents without re-implementing the state machine.
- **Classification catalog is data-driven** (JSON-like Python/TS structures) so administrators can extend it without code changes, and so mobile/desktop agents (once built) share the same category definitions as the browser extension.
- **Device tokens are scoped narrowly**: a device can submit usage events and fetch its own rules, nothing else. Parent/student dashboard sessions use full JWT auth with RBAC.
- **Notifications go through adapters** (`services/notification-worker/app/adapters/`) so swapping SendGrid/Twilio/FCM for another vendor doesn't touch business logic, and secrets stay server-side only.
- **Offline-first browser/agent design**: usage events carry a client-generated idempotency key so re-sending queued events after reconnect cannot double count.
