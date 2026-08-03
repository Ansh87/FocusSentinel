// Injected on <all_urls> (see manifest.json content_scripts). Renders the
// non-punitive progress notice and the two formal warnings directly in the
// page, per docs/USER_FLOWS.md — the student always sees what's happening
// and why, never a silent block.

function ensureBanner() {
  let el = document.getElementById("focussentinel-banner");
  if (!el) {
    el = document.createElement("div");
    el.id = "focussentinel-banner";
    el.setAttribute(
      "style",
      "position:fixed;top:0;left:0;right:0;z-index:2147483647;" +
        "font-family:system-ui,-apple-system,sans-serif;padding:12px 16px;" +
        "display:flex;align-items:center;justify-content:space-between;" +
        "box-shadow:0 2px 8px rgba(0,0,0,0.15);"
    );
    document.documentElement.appendChild(el);
  }
  return el;
}

function styleFor(level) {
  if (level === "warning_two") return { bg: "#7c2d12", fg: "#fff" };
  if (level === "warning_one") return { bg: "#b45309", fg: "#fff" };
  return { bg: "#1e3a8a", fg: "#fff" };
}

chrome.runtime.onMessage.addListener((message) => {
  if (message.type !== "focussentinel:evaluation") return;
  const { level, evaluation } = message;
  if (level === "restricted") return; // the redirect to restriction.html handles this case

  const banner = ensureBanner();
  const { bg, fg } = styleFor(level);
  banner.style.background = bg;
  banner.style.color = fg;

  const text = document.createElement("span");
  text.textContent = evaluation.message;

  const actions = document.createElement("div");

  const requestMoreBtn = document.createElement("button");
  requestMoreBtn.textContent = "Request more time";
  requestMoreBtn.setAttribute(
    "style",
    "margin-left:12px;background:#fff;color:#111;border:none;border-radius:4px;padding:6px 10px;cursor:pointer;"
  );
  requestMoreBtn.onclick = () => {
    chrome.runtime.sendMessage({ type: "focussentinel:requestExtension", identifier: evaluation.identifier });
  };

  const dismissBtn = document.createElement("button");
  dismissBtn.textContent = "Dismiss";
  dismissBtn.setAttribute(
    "style",
    "margin-left:8px;background:transparent;color:inherit;border:1px solid currentColor;border-radius:4px;padding:6px 10px;cursor:pointer;"
  );
  dismissBtn.onclick = () => banner.remove();

  actions.appendChild(requestMoreBtn);
  actions.appendChild(dismissBtn);

  banner.innerHTML = "";
  banner.appendChild(text);
  banner.appendChild(actions);
});
