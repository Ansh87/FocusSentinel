# FocusSentinel — Chrome/Edge extension (Manifest V3)

Real, working implementation for Phase 1. What it actually does:

- Tracks active-tab time only when the tab is active, its window is focused, and the system is not idle/locked (`lib/activeTimeTracker.js`, `background/service-worker.js`).
- Classifies domains against a maintained catalog (`lib/classifier.js`) — TikTok, YouTube Shorts, Instagram/Facebook Reels, Twitch, Discord, Reddit, Netflix, generic YouTube, etc.
- Drops any session under 3 seconds as a false positive.
- Queues usage segments locally (`chrome.storage.local`) and syncs them in batches every 30 seconds; queued segments survive being offline and are sent in order once reconnected, with server-side idempotency keys preventing double counting.
- Applies real blocking via `declarativeNetRequest` once the API returns a `restricted` evaluation, redirecting to a bundled restriction page — this is genuine enforcement for the browser, not a simulation.
- Shows the progress notice and both formal warnings directly on the page via a content script banner.

## What it does not do

- It cannot see or block activity inside native mobile/desktop apps (TikTok's iOS app, for example) — that requires the platform-specific agents described in `docs/KNOWN_LIMITATIONS.md`.
- It does not read page content, form fields, messages, or keystrokes on any site.

## Local setup

1. Run the API (`services/api`) and make note of its base URL (default `http://localhost:8000`).
2. Register a device for a student via `POST /devices/register` (or use the seeded demo device — see `database/seed/`) to get a device token.
3. Load the extension unpacked: `chrome://extensions` → Developer mode → "Load unpacked" → select `apps/browser-extension/`.
4. Open the service worker console (`chrome://extensions` → FocusSentinel → "service worker") and run:
   ```js
   chrome.runtime.sendMessage({
     type: "focussentinel:configure",
     config: {
       apiBaseUrl: "http://localhost:8000",
       deviceId: "<device id from registration>",
       deviceToken: "<device token from registration>",
       studentId: "<student id>",
     },
   });
   ```
5. Visit `tiktok.com` or `youtube.com/shorts` and watch usage accumulate in the dashboard.

## Tests

```bash
cd apps/browser-extension
npm install
npm test
```
