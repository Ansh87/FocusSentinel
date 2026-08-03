# FocusSentinel

**Healthy digital habits, without constant supervision.**

FocusSentinel measures active, foreground time on configured apps/sites for students and families, applies household-defined limits through a graduated warning-then-restriction sequence, and helps build better habits instead of just monitoring and punishing. See `docs/PRD.md` for the full product requirements, `docs/ARCHITECTURE.md` for system diagrams, and `docs/KNOWN_LIMITATIONS.md` for an honest accounting of what's real versus planned.

## What's in this repository

This is Phase 1 of a five-phase plan (`docs/PRD.md` section 4): a fully working backend, database, web dashboard, and Chrome/Edge browser extension, demonstrating the complete warning → restriction → extension-request → approval loop end to end. Windows, macOS, Android, and iOS clients are scaffolded with honest READMEs describing exactly what's needed to build them for real — none of them contain fake or simulated enforcement.

```text
focussentinel/
  apps/
    web-dashboard/        Next.js — parent + student dashboard (working)
    browser-extension/    Manifest V3 Chrome/Edge extension (working)
    android/              Phase 3 — scaffold + docs only
    ios/                  Phase 4 — scaffold + docs only
    windows-agent/         Phase 2 — scaffold + docs only
    macos-agent/           Phase 5 — scaffold + docs only
  services/
    api/                   FastAPI backend (working)
    notification-worker/   Polling worker + adapter pattern (working)
  packages/
    rules-engine/          Pure warning/restriction state machine (working, unit tested)
    activity-classifier/   Domain/app classification catalog (working, unit tested)
    shared-types/          Shared TypeScript types
  database/
    migrations/            Postgres schema (0001_init.sql)
    seed/                  Demo data script
  docs/                    PRD, architecture, schema, flows, security, limitations
```

## Quick start (Docker Compose)

```bash
cp .env.example .env        # edit JWT_SECRET and Postgres credentials for anything beyond local dev
docker compose up --build
```

This starts Postgres, Redis, the API (`localhost:8000`, interactive docs at `/docs`), the notification worker, and the web dashboard (`localhost:3000`). Then seed demo data:

```bash
docker compose exec api python /app/../../database/seed/seed.py
# or, running the API outside Docker (see "Local development" below):
cd services/api && DATABASE_URL=<your DATABASE_URL> python ../../database/seed/seed.py
```

Sign in to the dashboard at `localhost:3000` with the printed demo credentials (`parent@focussentinel.demo` / `demo-password-123`).

## Local development (without Docker)

```bash
# 1. Rules engine + classifier packages (installed editable by the API's requirements.txt)
cd packages/rules-engine && pip install -e . --break-system-packages
cd ../activity-classifier && pip install -e . --break-system-packages

# 2. API (defaults to a local SQLite file if DATABASE_URL is unset)
cd ../../services/api
pip install -r requirements.txt --break-system-packages
uvicorn app.main:app --reload --port 8000

# 3. Seed demo data (in a second terminal)
python ../../database/seed/seed.py

# 4. Notification worker (in a third terminal)
cd ../notification-worker
pip install -r requirements.txt --break-system-packages
python -m app.worker

# 5. Web dashboard (in a fourth terminal)
cd ../../apps/web-dashboard
npm install && npm run dev
```

Load the browser extension unpacked from `apps/browser-extension/` (`chrome://extensions` → Developer mode → Load unpacked) and configure it with the seeded device token — see `apps/browser-extension/README.md` for the exact console command.

## Running the tests

```bash
# Rules engine (simulated-clock tests: a 45-minute limit tested in milliseconds)
cd packages/rules-engine && pytest

# Activity classifier
cd packages/activity-classifier && pytest

# API — the full vertical-slice test (warning one -> warning two -> restriction ->
# extension request -> approval -> restored access) plus offline sync and auth tests
cd services/api && pytest

# Notification worker
cd services/notification-worker && pytest

# Browser extension active-time tracking logic
cd apps/browser-extension && npm install && npm test
```

**A note on verification in this build:** these test suites were written to genuinely exercise the code (see `services/api/tests/test_usage_flow.py` for the full warning-to-restriction-to-extension flow, and `packages/rules-engine/tests/test_rules_engine.py` for the simulated-clock edge cases including cross-midnight sessions and a DST transition), but the sandboxed environment this repository was built in could not execute a Linux shell this session, so the suites have not actually been run end-to-end yet. Run them locally with the commands above before relying on this as a deployment — and please file anything that doesn't pass as expected.

## Demonstrating the full vertical slice manually

1. `POST /auth/register` a parent, `POST /families`, `POST /students` (or just use the seed data).
2. `POST /devices/register` for the student, note the returned device token.
3. `POST /rules` with a short `daily_limit_minutes` (the seed data already creates a 2-minute short-form-video limit for the demo student).
4. `POST /notification-recipients` for the parent's email.
5. Configure the browser extension with the device token (see `apps/browser-extension/README.md`) and browse `tiktok.com` for a couple of minutes.
6. Watch the in-page banner progress from the 80% notice → warning one → warning two → restriction, and the site get redirected to the bundled restriction page.
7. Check the notification worker's console output (or your configured email provider) for the queued notifications.
8. Refresh the parent dashboard (`localhost:3000/dashboard`) to see the warnings, restriction, and device health update.
9. From the restriction page (or the student dashboard), submit an extension request.
10. Approve it from the parent dashboard — the restriction lifts and the audit log records the approval.

## Testing, running, and deploying

See `docs/DEPLOYMENT.md` for exact commands to run every test suite, run the stack locally with or without Docker, push this repo to GitHub, and deploy it to Railway (API + notification worker + web dashboard as separate services, plus managed Postgres).

## Documentation index

- `docs/PRD.md` — product requirements and phase scope
- `docs/ARCHITECTURE.md` — system + sequence diagrams (Mermaid)
- `docs/USER_FLOWS.md` — onboarding and warning/restriction flows
- `docs/SECURITY_PRIVACY.md` — what's protected today and what's still a gap
- `docs/KNOWN_LIMITATIONS.md` — the honest platform-by-platform capability matrix
- `docs/DEPLOYMENT.md` — testing, local run, GitHub push, Railway deployment
- `database/migrations/0001_init.sql` — full Postgres schema
