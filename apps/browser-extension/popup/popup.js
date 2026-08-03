async function render() {
  const evaluations = (await chrome.runtime.sendMessage({ type: "focussentinel:getState" })) || {};
  const container = document.getElementById("rows");
  container.innerHTML = "";

  const entries = Object.values(evaluations);
  if (entries.length === 0) {
    container.innerHTML = '<div class="row">No monitored activity yet today.</div>';
    return;
  }

  for (const evaluation of entries) {
    const row = document.createElement("div");
    row.className = "row";
    const remaining =
      evaluation.minutes_remaining != null ? `${Math.round(evaluation.minutes_remaining)} min left` : "no limit";
    row.innerHTML = `<span>${evaluation.identifier}</span><span>${remaining}</span>`;
    container.appendChild(row);
  }
}

render();
