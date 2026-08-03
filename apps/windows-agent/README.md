# FocusSentinel — Windows agent (Phase 2, not implemented in this build)

**Status: scaffold only. No working code ships here yet.** This directory exists so the monorepo layout matches the target architecture; do not present anything in this folder as functional to a user.

## What it will require when built

- A signed **.NET Worker Service** (`Microsoft.Extensions.Hosting.WindowsServices`) running under an administrator-installed service, per `docs/PRD.md` Phase 2.
- Foreground-window / active-process detection via the Win32 API (`GetForegroundWindow`, `GetWindowThreadProcessId`) polled on an interval, matched against `packages/activity-classifier`'s process catalog (Steam, Epic Games Launcher, Roblox, Minecraft, Fortnite, etc.).
- Idle detection via `GetLastInputInfo` to pause counting when the machine is locked or unattended.
- A local SQLite queue for offline usage events, synced to `POST /usage-events/batch` using the same device-token auth scheme as the browser extension (`services/api/app/deps.py::get_current_device`).
- A visible system-tray icon (per spec — no hidden/stealth processes) and native Windows toast notifications for the warning sequence.
- Process termination only after the second warning's grace period elapses, and only if `immediate_enforcement` isn't set to skip the grace period.

## Why it isn't built yet

This build focused Phase 1 on the pieces required for the working vertical slice (API, Postgres, dashboard, browser extension). A Windows agent needs a Windows build/signing environment and cannot be meaningfully tested inside this repo's Linux-based tooling. Building it without that verification would risk shipping enforcement code that silently doesn't work — which conflicts with this product's core promise never to claim protection it doesn't actually provide.

## Suggested next steps

1. Scaffold a `Microsoft.Extensions.Hosting` Worker Service project (`dotnet new worker`).
2. Implement the foreground-process poller and wire it to `packages/activity-classifier`'s catalog (port the Python catalog to a small JSON file both languages can read, to avoid drift).
3. Reuse `packages/rules-engine`'s state machine logic by porting it to C# (the algorithm in `rules_engine/engine.py` is intentionally pure/stateless and should translate directly), or expose it as a small local HTTP sidecar if code-sharing across languages is preferred.
4. Add device registration to the onboarding flow in `apps/web-dashboard`.
