# FocusSentinel — Product Requirements Document

**Tagline:** Healthy digital habits, without constant supervision.

## 1. Problem and objective

Students and families need help building healthier relationships with short-form video, games, and social media, without turning a household device into a surveillance target. FocusSentinel measures *active, foreground* time on configured apps/sites, applies household-defined limits, and uses a graduated warning-then-restriction sequence instead of silent blocking or shaming reports.

FocusSentinel is explicitly **not** spyware. It does not read messages, capture screens or keystrokes, or hide from the person using the device. Every measurement it performs is disclosed to the student in the product itself.

## 2. Non-negotiable design principles

1. **Consent and visibility.** The student always sees a monitoring status indicator and can view exactly what is tracked.
2. **Real functionality only.** Every feature either works end-to-end, is explicitly labeled "requires OS permission not yet granted," or is explicitly labeled "platform limitation — not implemented." The product never claims enforcement it cannot perform.
3. **Grace over punishment.** Two warnings with a save-progress grace period precede any restriction. Reports use neutral, non-shaming language.
4. **Minimum necessary data.** Usage events store identifiers, category, start/end timestamps, and duration — never content, screenshots, keystrokes, or messages.
5. **Household configurability.** Parents/guardians and (age-appropriately) students configure limits together; suggested profiles are editable defaults, not prescriptions.

## 3. Roles

- **Parent/Guardian** — creates the family, registers students and devices, configures rules and notification recipients, reviews history, approves/denies extensions.
- **Student** — sees live status, remaining time, warnings, and can request more time with a reason. Never secretly monitored.
- **System/Service accounts** — device agents and the browser extension authenticate as a device bound to a student, with a narrow token scope (usage-event ingestion + rule fetch only).

## 4. Scope by phase

| Phase | Deliverable | Status in this repo |
|---|---|---|
| 1 | API, Postgres, web dashboard, Chrome/Edge extension, website tracking, 2-warning flow, restriction, email notification, demo data, Docker Compose | **Implemented** (this build) |
| 2 | Windows agent, game/app detection, Windows warnings/restriction, SMS, offline sync, device health | Scaffolded only — see `apps/windows-agent/README.md` |
| 3 | Android client, usage tracking, Play-compliant enforcement, push, permission health | Scaffolded only — see `apps/android/README.md` |
| 4 | iOS app, Screen Time / FamilyControls / DeviceActivity / ManagedSettings integration | Scaffolded only — see `apps/ios/README.md` |
| 5 | macOS agent, advanced reporting, household schedules, multi-student, school deployment | Not started |

"Scaffolded only" means: directory structure, README describing the real OS APIs required, and non-functional starter project files. No simulated blocking is presented as real.

## 5. Vertical slice (what actually runs in this repo)

1. Parent registers a family + student via the API (or seeded demo data).
2. Parent adds TikTok and YouTube Shorts as monitored activities and sets a short test limit (e.g., 2 minutes, using the simulated clock in tests; real minutes in the running demo).
3. The browser extension measures active-tab foreground time on `tiktok.com` and `youtube.com/shorts` and batches usage events to the API.
4. At 80% of the limit the extension shows a non-punitive progress notice (not a formal warning).
5. At 100% the API records **Warning 1**, the extension displays it, and a notification is queued.
6. After the configured grace period the API records **Warning 2** with a countdown.
7. After the grace countdown, the API creates a **restriction event**; the extension blocks the domain via `declarativeNetRequest` and shows the restriction page with the reason and reset time.
8. The notification worker sends an email (and SMS if configured) to authorized recipients, deduplicated so repeats don't spam.
9. The dashboard reflects usage, warnings, and the restriction in near real time.
10. The student submits an extension request with a reason; the parent approves a fixed amount of extra time from the dashboard.
11. The API lifts the restriction for the approved window and logs the approval in the audit log.

## 6. Acceptance criteria (Phase 1)

See `docs/KNOWN_LIMITATIONS.md` for what is out of scope, and the root `README.md` for how to run and verify each criterion in section 22 of the original spec.
