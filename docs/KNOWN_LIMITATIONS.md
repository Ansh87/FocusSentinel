# FocusSentinel — Known Platform Limitations

This document is the single source of truth for what actually works versus what's planned. If something isn't listed here as working, assume it isn't — the product must never claim enforcement it hasn't implemented.

## Implemented and working today (Phase 1)

| Capability | Status |
|---|---|
| Parent/student accounts, JWT auth, RBAC | Working |
| Family/student/device management API | Working |
| Rules engine: daily limits, schedules, day-of-week, progress notice, two warnings, restriction, extensions | Working, unit + integration tested |
| Website tracking via Chrome/Edge extension (Manifest V3) | Working — measures active-tab foreground time only |
| Real website blocking via `declarativeNetRequest` | Working for the browser only |
| Two-warning sequence with in-page banners | Working |
| Restriction page with reset time + extension request form | Working |
| Email notifications (console adapter by default) | Working; real SMTP/SendGrid require credentials you supply |
| Offline queueing + idempotent sync (browser extension) | Working |
| Dashboard: today's usage, warnings, restrictions, extension approval, device health | Working, minimal UI |
| Audit log | Working |

## Explicitly not implemented (by platform)

### Windows agent
Not built (see `apps/windows-agent/README.md`). No foreground-process detection, no native warnings, no game/app blocking on Windows exists in this repo yet.

### macOS agent
Not built (see `apps/macos-agent/README.md`). Even once built, macOS offers no first-party API for a third-party app to reliably hard-block another native application the way iOS's Screen Time APIs do — expect monitoring and notifications to be solid, and application-level blocking to be best-effort at most.

### Android app
Not built (see `apps/android/README.md`). Real Android usage tracking requires the user to explicitly grant Usage Access in system settings — this can never be silent or automatic, by Android design and by this product's own rule against secret monitoring. Enforcement must stay within Google Play–compliant mechanisms, which rules out repurposing Accessibility Services to inspect other apps' content.

### iOS/iPadOS app
Not built (see `apps/ios/README.md`). Real enforcement requires Apple's Family Controls entitlement (Apple must approve the request) plus a genuine parent/guardian Screen Time authorization flow. Apple's app-selection model returns opaque tokens rather than raw identifiers — FocusSentinel cannot independently verify or relabel what a family selected on iOS beyond what the OS reports, and cannot distinguish, e.g., "Reels" from general Instagram browsing inside the app; the whole app is the unit of control there.

## Cross-cutting limitations (all platforms)

- **No screenshot, keystroke, message, or content capture anywhere** — this is by design, not a missing feature.
- **Short-form video sub-detection only works in the browser.** Inside a native mobile app, FocusSentinel (once mobile clients exist) can only measure and limit at the whole-app level unless the platform vendor exposes finer-grained activity types.
- **A student who uninstalls, disables, or grants no permission to a client cannot be monitored on that device.** FocusSentinel reports this state plainly (`device_health_events`) rather than attempting to hide, self-reinstall, or otherwise behave like malware — that is a hard product boundary, not a gap to "fix" with more aggressive persistence.
- **API rate limiting, refresh-token revocation lists, recipient verification, and scheduled data retention purges are not yet implemented** — see `docs/SECURITY_PRIVACY.md` for the full list.
- **No legal/regulatory compliance claim (COPPA, FERPA, GDPR, state student-privacy laws, etc.) has been made or reviewed for this codebase.** Anyone deploying this for real families or a school should get independent legal review first.

## What "restricted" means today, precisely

For the browser extension: a `declarativeNetRequest` rule redirects the matched domain to a bundled, informative restriction page until a parent lifts it (via extension approval or, in a future pass, a parent-PIN unlock). It does not close other tabs, does not affect other domains, and does not affect the same site accessed from a native app on the same device.
