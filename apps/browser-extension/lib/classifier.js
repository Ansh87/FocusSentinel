// Mirrors packages/activity-classifier/activity_classifier/catalog.py.
// Kept as a hand-synced copy (not a build-time import) so the extension has
// zero build step and can be loaded unpacked for review; see that Python
// file's docstring for the canonical source used by the backend.
//
// Adding an entry here does not track anything by itself — the background
// service worker only evaluates domains the family has actually enabled
// (see sync.js, which pulls the family's active rules from the API).

export const DOMAIN_CATALOG = [
  { key: "tiktok.com", label: "TikTok", category: "short_form_video", matchType: "domain" },
  { key: "youtube.com/shorts", label: "YouTube Shorts", category: "short_form_video", matchType: "url_pattern" },
  { key: "instagram.com/reels", label: "Instagram Reels", category: "short_form_video", matchType: "url_pattern" },
  { key: "facebook.com/reel", label: "Facebook Reels", category: "short_form_video", matchType: "url_pattern" },
  { key: "instagram.com", label: "Instagram", category: "social_media", matchType: "domain" },
  { key: "facebook.com", label: "Facebook", category: "social_media", matchType: "domain" },
  { key: "twitch.tv", label: "Twitch", category: "entertainment_video", matchType: "domain" },
  { key: "discord.com", label: "Discord", category: "messaging", matchType: "domain", classification: "neutral" },
  { key: "reddit.com", label: "Reddit", category: "social_media", matchType: "domain" },
  { key: "netflix.com", label: "Netflix", category: "entertainment_video", matchType: "domain" },
  { key: "youtube.com", label: "YouTube", category: "entertainment_video", matchType: "domain", classification: "neutral" },
];

export function normalizeHostname(hostname) {
  return hostname.toLowerCase().replace(/^www\./, "");
}

/**
 * Longest-match-wins classification for a URL, same semantics as
 * activity_classifier.classify_domain on the backend.
 * @param {string} hostname
 * @param {string} path
 */
export function classifyUrl(hostname, path = "") {
  const host = normalizeHostname(hostname);
  const candidates = DOMAIN_CATALOG.filter((c) => {
    if (c.matchType === "domain") return host === c.key;
    if (c.matchType === "url_pattern") return `${host}${path}`.startsWith(c.key);
    return false;
  });
  if (candidates.length === 0) return null;
  return candidates.reduce((best, c) => (c.key.length > best.key.length ? c : best));
}

/** Also exported for custom, family-added domains merged in at runtime by sync.js. */
export function mergeCustomDomains(customEntries) {
  return [...DOMAIN_CATALOG, ...customEntries];
}
