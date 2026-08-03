// Offline-first sync: usage segments are appended to a local queue in
// chrome.storage.local immediately, then flushed to the API in batches.
// If the network is unavailable, segments simply accumulate locally and are
// sent (in chronological order) the next time a flush succeeds — mirroring
// the offline behavior required in docs/PRD.md section 15.

const QUEUE_KEY = "focussentinel_queue_v1";
const CONFIG_KEY = "focussentinel_config_v1"; // { apiBaseUrl, deviceId, deviceToken }

export async function getConfig() {
  const { [CONFIG_KEY]: config } = await chrome.storage.local.get(CONFIG_KEY);
  return config || null;
}

export async function setConfig(config) {
  await chrome.storage.local.set({ [CONFIG_KEY]: config });
}

export async function enqueueSegment(segment) {
  const { [QUEUE_KEY]: queue = [] } = await chrome.storage.local.get(QUEUE_KEY);
  queue.push(segment);
  await chrome.storage.local.set({ [QUEUE_KEY]: queue });
}

export async function peekQueue() {
  const { [QUEUE_KEY]: queue = [] } = await chrome.storage.local.get(QUEUE_KEY);
  return queue;
}

async function removeSent(sentKeys) {
  const { [QUEUE_KEY]: queue = [] } = await chrome.storage.local.get(QUEUE_KEY);
  const remaining = queue.filter((s) => !sentKeys.has(s.idempotencyKey));
  await chrome.storage.local.set({ [QUEUE_KEY]: remaining });
}

/**
 * Sends whatever is queued, in chronological order, and returns the parsed
 * evaluation results so the caller (service worker) can react to
 * warning/restriction levels. On any network failure the queue is left
 * intact for the next attempt — nothing is lost or double-sent, because the
 * server treats idempotencyKey as a dedup key.
 */
export async function flushQueue(fetchImpl = fetch) {
  const config = await getConfig();
  if (!config || !config.apiBaseUrl || !config.deviceToken) {
    return { flushed: false, reason: "not_configured" };
  }

  const queue = await peekQueue();
  if (queue.length === 0) return { flushed: true, evaluations: [] };

  const events = [...queue]
    .sort((a, b) => new Date(a.startedAt) - new Date(b.startedAt))
    .map((s) => ({
      identifier: s.identifier,
      started_at: s.startedAt,
      ended_at: s.endedAt,
      active_duration_seconds: s.activeDurationSeconds,
      classification_source: "catalog",
      idempotency_key: s.idempotencyKey,
    }));

  try {
    const resp = await fetchImpl(`${config.apiBaseUrl}/usage-events/batch`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${config.deviceToken}`,
      },
      body: JSON.stringify({ device_id: config.deviceId, events }),
    });

    if (!resp.ok) {
      return { flushed: false, reason: `http_${resp.status}` };
    }

    const body = await resp.json();
    await removeSent(new Set(events.map((e) => e.idempotency_key)));
    return { flushed: true, evaluations: body.evaluations || [] };
  } catch (err) {
    // Offline or backend unreachable — queue stays intact for the next alarm tick.
    return { flushed: false, reason: "network_error", error: String(err) };
  }
}
