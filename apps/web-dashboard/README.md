# FocusSentinel — Web dashboard

Minimal, functional Next.js dashboard for Phase 1: sign in, view today's usage by category, see active warnings/restrictions, approve or deny extension requests, and check device health. Talks directly to the FastAPI backend over `NEXT_PUBLIC_API_BASE_URL`.

## Known simplifications in this build

- No onboarding wizard UI yet (the API supports every call the wizard in `docs/USER_FLOWS.md` would need — family/student/device/rule/recipient creation — but the guided multi-step screen itself isn't built).
- The student view is addressed by student ID (shared by a parent) rather than through a full student account-invite flow.
- Auth token is stored in `localStorage`; production should move to an httpOnly cookie session — see `docs/SECURITY_PRIVACY.md`.

## Run locally

```bash
cd apps/web-dashboard
npm install
npm run dev
```

Requires the API running at `NEXT_PUBLIC_API_BASE_URL` (defaults to `http://localhost:8000`).
