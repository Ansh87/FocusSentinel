import { getConfig } from "../lib/sync.js";

const params = new URLSearchParams(location.search);
const identifier = params.get("identifier") || "this activity";
document.getElementById("identifier").textContent = identifier;

async function loadEvaluation() {
  const evaluations = await chrome.runtime.sendMessage({ type: "focussentinel:getState" });
  const evaluation = evaluations && evaluations[identifier];
  document.getElementById("reason-text").textContent =
    (evaluation && evaluation.message) ||
    "This activity has reached today's limit. You can ask a parent or guardian for more time.";
}
loadEvaluation();

document.getElementById("request-time-btn").addEventListener("click", () => {
  document.getElementById("extension-form").style.display = "block";
});

document.getElementById("parent-pin-btn").addEventListener("click", () => {
  document.getElementById("status-text").textContent =
    "Parent PIN unlock happens from the FocusSentinel dashboard — open it to approve access directly.";
});

document.getElementById("extension-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const config = await getConfig();
  const statusEl = document.getElementById("status-text");
  if (!config || !config.apiBaseUrl || !config.studentId) {
    statusEl.textContent = "This device isn't fully set up yet — ask a parent to finish onboarding.";
    return;
  }

  try {
    const resp = await fetch(`${config.apiBaseUrl}/extension-requests`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${config.userAccessToken || ""}` },
      body: JSON.stringify({
        student_id: config.studentId,
        requested_minutes: Number(document.getElementById("minutes").value),
        reason_code: document.getElementById("reason").value,
        explanation: document.getElementById("explanation").value,
      }),
    });
    if (resp.ok) {
      statusEl.textContent = "Request sent. You'll be notified once a parent or guardian responds.";
    } else {
      statusEl.textContent = "Could not send the request right now. Please try again in a moment.";
    }
  } catch {
    statusEl.textContent = "You appear to be offline — this request will need a connection to send.";
  }
});
