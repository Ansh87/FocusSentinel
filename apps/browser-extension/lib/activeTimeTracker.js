// Pure, dependency-injected active-time tracker so it can be unit tested
// without a real browser (see tests/activeTimeTracker.test.js). The
// background service worker (background/service-worker.js) is a thin
// wrapper that feeds real chrome.* events into this class and forwards
// finished segments to sync.js.
//
// Counting rules implemented here (see docs/PRD.md section 5):
//  - only counts while the tab is the active tab of a focused window
//  - pauses on chrome.idle 'idle'/'locked' state
//  - a session shorter than FALSE_POSITIVE_THRESHOLD_SECONDS is dropped
//    entirely rather than reported, to filter out flicker/false positives

export const FALSE_POSITIVE_THRESHOLD_SECONDS = 3;

export class ActiveTimeTracker {
  /**
   * @param {{ now: () => number, classify: (hostname: string, path: string) => ({key:string,category:string}|null), onSegment: (segment: object) => void }} deps
   */
  constructor({ now, classify, onSegment }) {
    this._now = now;
    this._classify = classify;
    this._onSegment = onSegment;
    this._session = null; // { identifier, category, startedAtMs }
    this._windowFocused = true;
    this._idleState = "active"; // 'active' | 'idle' | 'locked'
  }

  /** Called when the active tab in the focused window changes to a new URL, or on startup. */
  onActiveUrlChanged(hostname, path) {
    this._closeSession();
    if (!hostname || !this._windowFocused || this._idleState !== "active") return;

    const match = this._classify(hostname, path);
    if (!match) return;

    this._session = {
      identifier: match.key,
      category: match.category,
      startedAtMs: this._now(),
    };
  }

  onWindowFocusChanged(focused) {
    this._windowFocused = focused;
    if (!focused) this._closeSession();
  }

  onIdleStateChanged(state) {
    this._idleState = state;
    if (state !== "active") this._closeSession();
  }

  /** No URL change, but useful for periodic flush of long-running sessions (e.g. every 60s) so a crash doesn't lose more than a minute of data. */
  flushIfLongRunning(maxSegmentSeconds = 60) {
    if (!this._session) return;
    const elapsed = (this._now() - this._session.startedAtMs) / 1000;
    if (elapsed >= maxSegmentSeconds) {
      const identifier = this._session.identifier;
      const category = this._session.category;
      this._emitSegment(this._session.startedAtMs, this._now(), identifier, category);
      this._session = { identifier, category, startedAtMs: this._now() };
    }
  }

  _closeSession() {
    if (!this._session) return;
    const { identifier, category, startedAtMs } = this._session;
    this._emitSegment(startedAtMs, this._now(), identifier, category);
    this._session = null;
  }

  _emitSegment(startedAtMs, endedAtMs, identifier, category) {
    const seconds = Math.round((endedAtMs - startedAtMs) / 1000);
    if (seconds < FALSE_POSITIVE_THRESHOLD_SECONDS) return; // drop false positives
    this._onSegment({
      identifier,
      category,
      startedAt: new Date(startedAtMs).toISOString(),
      endedAt: new Date(endedAtMs).toISOString(),
      activeDurationSeconds: seconds,
      idempotencyKey: `${identifier}-${startedAtMs}`,
    });
  }
}
