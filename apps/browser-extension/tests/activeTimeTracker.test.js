import { describe, it, expect, vi } from "vitest";
import { ActiveTimeTracker, FALSE_POSITIVE_THRESHOLD_SECONDS } from "../lib/activeTimeTracker.js";

function classify(hostname) {
  if (hostname === "tiktok.com") return { key: "tiktok.com", category: "short_form_video" };
  if (hostname === "example.com") return null;
  return null;
}

function makeClock(startMs = 1_700_000_000_000) {
  let t = startMs;
  return { advance: (ms) => (t += ms), now: () => t };
}

describe("ActiveTimeTracker", () => {
  it("emits a segment when navigating away from a tracked domain after enough time", () => {
    const clock = makeClock();
    const segments = [];
    const tracker = new ActiveTimeTracker({ now: clock.now, classify, onSegment: (s) => segments.push(s) });

    tracker.onActiveUrlChanged("tiktok.com", "/");
    clock.advance(10_000); // 10s
    tracker.onActiveUrlChanged("example.com", "/"); // navigate away, untracked

    expect(segments).toHaveLength(1);
    expect(segments[0].identifier).toBe("tiktok.com");
    expect(segments[0].activeDurationSeconds).toBe(10);
  });

  it("drops sessions shorter than the false-positive threshold", () => {
    const clock = makeClock();
    const segments = [];
    const tracker = new ActiveTimeTracker({ now: clock.now, classify, onSegment: (s) => segments.push(s) });

    tracker.onActiveUrlChanged("tiktok.com", "/");
    clock.advance((FALSE_POSITIVE_THRESHOLD_SECONDS - 1) * 1000);
    tracker.onActiveUrlChanged("example.com", "/");

    expect(segments).toHaveLength(0);
  });

  it("pauses counting when the window loses focus", () => {
    const clock = makeClock();
    const segments = [];
    const tracker = new ActiveTimeTracker({ now: clock.now, classify, onSegment: (s) => segments.push(s) });

    tracker.onActiveUrlChanged("tiktok.com", "/");
    clock.advance(5000);
    tracker.onWindowFocusChanged(false); // should close out a 5s segment
    clock.advance(60_000); // time passes while unfocused - must not be counted
    tracker.onWindowFocusChanged(true);

    expect(segments).toHaveLength(1);
    expect(segments[0].activeDurationSeconds).toBe(5);
  });

  it("pauses counting when the system goes idle or locks", () => {
    const clock = makeClock();
    const segments = [];
    const tracker = new ActiveTimeTracker({ now: clock.now, classify, onSegment: (s) => segments.push(s) });

    tracker.onActiveUrlChanged("tiktok.com", "/");
    clock.advance(8000);
    tracker.onIdleStateChanged("locked");
    clock.advance(120_000);
    tracker.onIdleStateChanged("active");

    expect(segments).toHaveLength(1);
    expect(segments[0].activeDurationSeconds).toBe(8);

    // Resuming does not automatically restart a session until a new
    // onActiveUrlChanged fires (the service worker re-queries the active tab
    // on idle-state-changed -> active in production code).
  });

  it("does not start a session for a domain with no monitoring rule", () => {
    const clock = makeClock();
    const segments = [];
    const tracker = new ActiveTimeTracker({ now: clock.now, classify, onSegment: (s) => segments.push(s) });

    tracker.onActiveUrlChanged("example.com", "/");
    clock.advance(30_000);
    tracker.onActiveUrlChanged("example.com", "/other");

    expect(segments).toHaveLength(0);
  });

  it("flushIfLongRunning splits a long session into hourly-safe chunks without losing time", () => {
    const clock = makeClock();
    const segments = [];
    const tracker = new ActiveTimeTracker({ now: clock.now, classify, onSegment: (s) => segments.push(s) });

    tracker.onActiveUrlChanged("tiktok.com", "/");
    clock.advance(60_000);
    tracker.flushIfLongRunning(60);
    clock.advance(30_000);
    tracker.onActiveUrlChanged("example.com", "/"); // close final partial segment

    const total = segments.reduce((sum, s) => sum + s.activeDurationSeconds, 0);
    expect(total).toBe(90);
    expect(segments).toHaveLength(2);
  });
});
