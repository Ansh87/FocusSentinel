# FocusSentinel — iOS/iPadOS app (Phase 4, not implemented in this build)

**Status: scaffold only. No working code ships here yet.**

## What it will require when built

- Swift/SwiftUI app using Apple's **Screen Time API family**: `FamilyControls` (authorization + app/category selection), `DeviceActivity` (monitoring schedules via a `DeviceActivityMonitor` extension), `ManagedSettings` (applying shields), and the `ShieldConfiguration`/`ShieldAction` extensions for the restriction UI and its buttons.
- The **Family Controls entitlement**, which Apple grants on request and which requires a proper parent/guardian authorization flow (`AuthorizationCenter.shared.requestAuthorization(for: .child)` or the individual flow, depending on setup) — this cannot be faked or bypassed.
- Apple's app/website selection model is privacy-preserving by design: the host app receives **opaque tokens**, not raw bundle IDs, for the family's selections. This means FocusSentinel cannot independently verify or relabel what a token represents the way it can for browser domains — the UI must reflect exactly what iOS reports.
- Where exact in-app detection (e.g., distinguishing Reels from browsing inside the Instagram app) isn't exposed by Apple's APIs, usage must be counted and limited at the whole-application level, and the product must say so plainly rather than imply finer-grained detection than iOS provides.
- Push notifications via APNs.

## Why it isn't built yet

This requires an Apple Developer account, the Family Controls entitlement (which Apple must approve), Xcode, and a real iOS device or simulator for the Screen Time APIs to do anything meaningful — none of which exist in this repo's toolchain. Per this product's core rule against claiming enforcement it hasn't verified, a from-scratch iOS build without that environment would either be non-functional or would have to fake results, both of which are explicitly disallowed by the spec.

## Suggested next steps

1. Enroll in the Apple Developer Program and request the Family Controls entitlement.
2. Scaffold the SwiftUI app plus the four required extensions (Device Activity Monitor, Device Activity Report, Shield Configuration, Shield Action) as separate extension targets in the same Xcode project.
3. Build the authorization and family-member picker screens first, since nothing else in the app can function without a granted `FamilyControls` authorization.
4. If the entitlement isn't available yet during development, build a clearly labeled "monitoring simulation" mode that is visually distinct (e.g., a persistent banner) and never represented as real enforcement, per spec section 9.
