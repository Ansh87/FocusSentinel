# FocusSentinel — macOS agent (Phase 5, not implemented in this build)

**Status: scaffold only. No working code ships here yet.**

## What it will require when built

- A visible **menu-bar agent** (Swift, `NSStatusItem`) — no hidden/background-only processes, per spec section 9.
- Foreground-app detection via `NSWorkspace.shared.frontmostApplication` and its bundle identifier, matched against the shared classification catalog.
- Idle detection via `CGEventSource.secondsSinceLastEventType` to pause counting when the Mac is unattended.
- Because macOS does not offer the same OS-level parental-control primitives as iOS's Screen Time APIs to third-party apps, **application blocking on macOS is inherently limited** — this agent can realistically provide monitoring, warnings, and notifications, plus browser-level blocking via the same Chrome/Edge extension already in `apps/browser-extension`, but should not claim to hard-block arbitrary native macOS apps. This must be disclosed in-product, not just in documentation, once built (see `docs/KNOWN_LIMITATIONS.md`).

## Why it isn't built yet

Building and code-signing a macOS agent requires Xcode and a macOS build environment unavailable in this repo's toolchain, and — per this product's non-negotiable design principle of never claiming enforcement it can't verify — nothing should be built here without the ability to test it end-to-end.

## Suggested next steps

1. Scaffold a menu-bar SwiftUI app with `LSUIElement` set appropriately (still visible in the menu bar, not hidden from Activity Monitor).
2. Port `packages/activity-classifier`'s catalog to Swift (or share a JSON catalog file across all agents).
3. Define what "restriction" means on macOS given API limits (e.g., quitting the app after grace period via `NSRunningApplication.terminate()`, which the user can still see and which respects the save-progress grace period) and disclose that limitation directly in the UI.
