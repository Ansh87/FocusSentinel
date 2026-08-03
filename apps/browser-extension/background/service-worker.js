import { classifyUrl } from "../lib/classifier.js";
import { ActiveTimeTracker } from "../lib/activeTimeTracker.js";
import { enqueueSegment, flushQueue, getConfig } from "../lib/sync.js";

const SYNC_ALARM = "focussentinel-sync";
const FLUSH_LONG_SESSION_ALARM = "focussentinel-flush-long-session";

let latestEvaluations = {}; // identifier -> evaluation, kept for the popup/restriction page

const tracker = new ActiveTimeTracker({
  now: () => Date.now(),
  classify: (hostname, path) => classifyUrl(hostname, path),
  onSegment: (segment) => {
    enqueueSegment(segment);
  },
});

function hostAndPathFromUrl(url) {
  try {
    const u = new URL(url);
    if (!["http:", "https:"].includes(u.protocol)) return { hostname: null, path: "" };
    return { hostname: u.hostname, path: u.pathname };
  } catch {
    return { hostname: null, path: "" };
  }
}

async function reevaluateActiveTab() {
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (!tab || !tab.url) {
    tracker.onActiveUrlChanged(null, "");
    return;
  }
  const { hostname, path } = hostAndPathFromUrl(tab.url);
  tracker.onActiveUrlChanged(hostname, path);
}

chrome.tabs.onActivated.addListener(reevaluateActiveTab);
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.url && tab.active) reevaluateActiveTab();
});
chrome.windows.onFocusChanged.addListener((windowId) => {
  tracker.onWindowFocusChanged(windowId !== chrome.windows.WINDOW_ID_NONE);
  if (windowId !== chrome.windows.WINDOW_ID_NONE) reevaluateActiveTab();
});
chrome.idle.onStateChanged.addListener((state) => {
  // 'active' | 'idle' | 'locked'
  tracker.onIdleStateChanged(state);
  if (state === "active") reevaluateActiveTab();
});

chrome.runtime.onInstalled.addListener(() => {
  chrome.idle.setDetectionInterval(60); // seconds of inactivity before 'idle'
  chrome.alarms.create(SYNC_ALARM, { periodInMinutes: 0.5 }); // sync every 30s
  chrome.alarms.create(FLUSH_LONG_SESSION_ALARM, { periodInMinutes: 1 });
  reevaluateActiveTab();
});

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name === SYNC_ALARM) {
    const result = await flushQueue();
    if (result.flushed) {
      await applyEvaluations(result.evaluations || []);
    }
  } else if (alarm.name === FLUSH_LONG_SESSION_ALARM) {
    tracker.flushIfLongRunning(60);
  }
});

async function applyEvaluations(evaluations) {
  for (const evaluation of evaluations) {
    latestEvaluations[evaluation.identifier] = evaluation;
    if (evaluation.level === "restricted") {
      await applyRestriction(evaluation.identifier);
      notifyActiveTabIfMatching(evaluation.identifier, "restricted", evaluation);
    } else if (evaluation.level === "warning_two") {
      notifyActiveTabIfMatching(evaluation.identifier, "warning_two", evaluation);
    } else if (evaluation.level === "warning_one") {
      notifyActiveTabIfMatching(evaluation.identifier, "warning_one", evaluation);
    }
  }
  await chrome.storage.local.set({ focussentinel_evaluations_v1: latestEvaluations });
}

async function notifyActiveTabIfMatching(identifier, level, evaluation) {
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (!tab || !tab.url) return;
  const { hostname, path } = hostAndPathFromUrl(tab.url);
  const match = classifyUrl(hostname || "", path);
  if (match && match.key === identifier) {
    chrome.tabs
      .sendMessage(tab.id, { type: "focussentinel:evaluation", level, evaluation })
      .catch(() => {
        /* content script may not be injected on this page type (e.g. chrome://) — non-fatal */
      });
  }
}

/**
 * Blocks the restricted domain using declarativeNetRequest, redirecting to
 * the bundled restriction page. This is real, working enforcement for
 * browser-controlled activity — see docs/KNOWN_LIMITATIONS.md for what this
 * cannot do (e.g. a native app for the same site on mobile).
 */
async function applyRestriction(identifier) {
  const config = await getConfig();
  const ruleId = stableRuleId(identifier);
  const redirectUrl = chrome.runtime.getURL(
    `pages/restriction.html?identifier=${encodeURIComponent(identifier)}`
  );

  await chrome.declarativeNetRequest.updateDynamicRules({
    removeRuleIds: [ruleId],
    addRules: [
      {
        id: ruleId,
        priority: 1,
        action: { type: "redirect", redirect: { url: redirectUrl } },
        condition: {
          urlFilter: `||${identifier.split("/")[0]}^`,
          resourceTypes: ["main_frame"],
        },
      },
    ],
  });
}

export async function liftRestriction(identifier) {
  const ruleId = stableRuleId(identifier);
  await chrome.declarativeNetRequest.updateDynamicRules({ removeRuleIds: [ruleId] });
}

function stableRuleId(identifier) {
  let hash = 0;
  for (let i = 0; i < identifier.length; i++) {
    hash = (hash * 31 + identifier.charCodeAt(i)) % 1_000_000;
  }
  return hash + 1; // rule ids must be >= 1
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "focussentinel:configure") {
    setConfigAndRespond(message.config, sendResponse);
    return true; // keep the message channel open for the async response
  }
  if (message.type === "focussentinel:getState") {
    chrome.storage.local.get("focussentinel_evaluations_v1").then((r) => sendResponse(r.focussentinel_evaluations_v1 || {}));
    return true;
  }
});

async function setConfigAndRespond(config, sendResponse) {
  const { setConfig } = await import("../lib/sync.js");
  await setConfig(config);
  sendResponse({ ok: true });
}
