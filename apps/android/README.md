# FocusSentinel — Android app (Phase 3, not implemented in this build)

**Status: scaffold only. No working code ships here yet.**

## What it will require when built

- **Kotlin** app using `UsageStatsManager` (requires the user to grant "Usage Access" in Settings — cannot be silently enabled, per spec section 9) for foreground-app time.
- Matching against `packages/activity-classifier`'s package-name catalog (`com.zhiliaoapp.musically` for TikTok, `com.instagram.android`, `com.roblox.client`, `com.mojang.minecraftpe`, etc.).
- Enforcement limited to **Google Play–compliant** mechanisms only: this explicitly rules out repurposing Accessibility Services to read screen content, and rules out any Device Admin capability Play policy doesn't allow for a consumer parental-control app. Where hard blocking isn't available through compliant APIs, the app must show a full-screen FocusSentinel restriction activity (an app-level overlay/redirect) rather than silently failing or pretending to block.
- A permission-health screen that plainly shows what's granted vs. missing — never silently degrading.
- Local Room/SQLite offline queue syncing to `POST /usage-events/batch`, matching the browser extension's device-token auth model.
- Firebase Cloud Messaging integration for push notifications.

## Why it isn't built yet

An Android build (Gradle, Kotlin, Play-compliant restricted APIs) needs an Android SDK/emulator environment this repo's toolchain doesn't have, and per this product's principle of never claiming enforcement it hasn't verified, nothing here should be presented as working without being run end-to-end on a device or emulator.

## Suggested next steps

1. Scaffold a Kotlin app (`./gradlew init` with the Android Gradle Plugin) requesting `PACKAGE_USAGE_STATS` via the Settings intent flow (never silently).
2. Port the classification catalog and rules-engine algorithm (or call a lightweight local endpoint backed by the same Python packages during development).
3. Build the permission-health and restriction-activity screens before wiring up any real enforcement, so the "never claim what isn't real" rule is enforced by construction.
