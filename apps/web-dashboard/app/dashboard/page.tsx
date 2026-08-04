"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, clearToken, isDemoFamily } from "../../lib/api";
import { Header } from "../../components/Header";

type Student = { id: string; display_name: string; family_id: string };
type TodayUsage = {
  total_seconds_by_category: Record<string, number>;
  total_seconds_by_rule: Record<string, number>;
  active_warnings: { level: number; rule_id: string }[];
  active_restrictions: { rule_id: string; reason: string; scheduled_reset_at: string }[];
};
type Website = {
  id: string;
  domain: string;
  url_pattern: string | null;
  label: string;
  category_id: string | null;
  source: string;
  is_custom: boolean;
};
type Rule = {
  id: string;
  student_id: string;
  name: string;
  scope_type: string;
  scope_category_key: string | null;
  websites: Website[];
  daily_limit_minutes: number | null;
  warning_one_at_minutes: number;
  active: boolean;
};

const CATEGORY_OPTIONS = [
  { key: "short_form_video", label: "Short-form video" },
  { key: "social_media", label: "Social media" },
  { key: "games", label: "Games" },
  { key: "entertainment_video", label: "Entertainment video" },
  { key: "messaging", label: "Messaging" },
  { key: "educational", label: "Educational" },
  { key: "productivity", label: "Productivity" },
  { key: "creative_work", label: "Creative work" },
  { key: "reading_research", label: "Reading & research" },
  { key: "other", label: "Other" },
];

function categoryLabel(key: string) {
  return CATEGORY_OPTIONS.find((c) => c.key === key)?.label || key.replace(/_/g, " ");
}

function ruleDisplayLabel(rule: Rule) {
  if (rule.websites.length > 0) return rule.websites.map((w) => w.label).join(" + ");
  if (rule.scope_category_key) return categoryLabel(rule.scope_category_key);
  return rule.name;
}

function usageStatusFor(usage: TodayUsage | null, ruleId: string, percent: number) {
  const restricted = usage?.active_restrictions.some((r) => r.rule_id === ruleId);
  if (restricted) return { text: "Restricted", cls: "restricted" };
  const w2 = usage?.active_warnings.some((w) => w.rule_id === ruleId && w.level === 2);
  if (w2) return { text: "Final warning issued", cls: "warning_two" };
  const w1 = usage?.active_warnings.some((w) => w.rule_id === ruleId && w.level === 1);
  if (w1) return { text: "First warning issued", cls: "warning_one" };
  if (percent >= 80) return { text: "Approaching limit", cls: "progress_notice" };
  return { text: "Within limit", cls: "none" };
}

export default function DashboardPage() {
  const router = useRouter();
  const [families, setFamilies] = useState<{ id: string; name: string }[]>([]);
  const [students, setStudents] = useState<Student[]>([]);
  const [selectedStudent, setSelectedStudent] = useState<string | null>(null);
  const [usage, setUsage] = useState<TodayUsage | null>(null);
  const [pendingRequests, setPendingRequests] = useState<any[]>([]);
  const [health, setHealth] = useState<any[]>([]);
  const [rules, setRules] = useState<Rule[]>([]);
  const [editLimits, setEditLimits] = useState<Record<string, string>>({});
  const [savingRuleId, setSavingRuleId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [familiesLoaded, setFamiliesLoaded] = useState(false);
  const [demoBusy, setDemoBusy] = useState(false);
  const [simSteps, setSimSteps] = useState<any[] | null>(null);
  const [simBusy, setSimBusy] = useState(false);

  const [showNewRule, setShowNewRule] = useState(false);
  const [scopeMode, setScopeMode] = useState<"category" | "websites">("category");
  const [newCategory, setNewCategory] = useState(CATEGORY_OPTIONS[0].key);
  const [newLimit, setNewLimit] = useState("30");
  const [creatingRule, setCreatingRule] = useState(false);
  const [ruleError, setRuleError] = useState<string | null>(null);

  const [websiteCatalog, setWebsiteCatalog] = useState<Website[]>([]);
  const [websiteSearch, setWebsiteSearch] = useState("");
  const [selectedWebsiteIds, setSelectedWebsiteIds] = useState<string[]>([]);
  const [customDomain, setCustomDomain] = useState("");
  const [customLabel, setCustomLabel] = useState("");
  const [addingCustomWebsite, setAddingCustomWebsite] = useState(false);

  async function loadFamilies() {
    try {
      const fams = await api.myFamilies();
      setFamilies(fams);
      if (fams.length > 0) {
        const s = await api.listStudents(fams[0].id);
        setStudents(s);
        if (s.length > 0) setSelectedStudent(s[0].id);
      } else {
        setStudents([]);
        setSelectedStudent(null);
      }
    } catch (e: any) {
      setError(e.message || "Please sign in again.");
    } finally {
      setFamiliesLoaded(true);
    }
  }

  useEffect(() => {
    loadFamilies();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!families[0]?.id) return;
    api
      .websitesCatalog(families[0].id)
      .then(setWebsiteCatalog)
      .catch(() => {
        /* non-fatal — the website multi-select just won't have options yet */
      });
  }, [families]);

  async function handleLoadDemo() {
    setDemoBusy(true);
    try {
      await api.loadDemo();
      await loadFamilies();
    } catch (e: any) {
      setError(e.message || "Could not load demo data.");
    } finally {
      setDemoBusy(false);
    }
  }

  async function handleResetDemo() {
    setDemoBusy(true);
    setSimSteps(null);
    try {
      await api.resetDemo();
      await loadFamilies();
      await refresh();
    } catch (e: any) {
      setError(e.message || "Could not reset demo data.");
    } finally {
      setDemoBusy(false);
    }
  }

  async function handleSimulate() {
    setSimBusy(true);
    setSimSteps(null);
    try {
      const result = await api.simulateActivity();
      setSimSteps(result.steps || []);
      await refresh();
    } catch (e: any) {
      setError(e.message || "Could not run the simulation.");
    } finally {
      setSimBusy(false);
    }
  }

  useEffect(() => {
    if (!selectedStudent) return;
    refresh();
    const interval = setInterval(refresh, 10_000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedStudent]);

  async function refresh() {
    if (!selectedStudent) return;
    try {
      const [u, reqs, h, r] = await Promise.all([
        api.usageToday(selectedStudent),
        api.listExtensionRequests(selectedStudent, "pending"),
        api.deviceHealth(selectedStudent),
        api.listRules(selectedStudent),
      ]);
      setUsage(u);
      setPendingRequests(reqs);
      setHealth(h);
      setRules(r);
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleApprove(id: string, minutes: number) {
    await api.approveExtension(id, minutes);
    refresh();
  }

  async function handleDeny(id: string) {
    await api.denyExtension(id);
    refresh();
  }

  function limitValueFor(rule: Rule) {
    return editLimits[rule.id] ?? String(rule.daily_limit_minutes ?? "");
  }

  async function handleSaveLimit(rule: Rule) {
    const raw = limitValueFor(rule);
    const minutes = Number(raw);
    if (!raw || Number.isNaN(minutes) || minutes <= 0) return;
    setSavingRuleId(rule.id);
    try {
      await api.updateRule(rule.id, { daily_limit_minutes: minutes });
      await refresh();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSavingRuleId(null);
    }
  }

  async function handleAddCustomWebsite() {
    if (!customDomain.trim() || !families[0]?.id) return;
    setAddingCustomWebsite(true);
    setRuleError(null);
    try {
      const site: Website = await api.addWebsite({
        family_id: families[0].id,
        domain: customDomain.trim(),
        label: customLabel.trim() || customDomain.trim(),
        category_key: "other",
      });
      setWebsiteCatalog((prev) => (prev.some((w) => w.id === site.id) ? prev : [...prev, site]));
      setSelectedWebsiteIds((prev) => (prev.includes(site.id) ? prev : [...prev, site.id]));
      setCustomDomain("");
      setCustomLabel("");
    } catch (e: any) {
      setRuleError(e.message || "Could not add that website — check the domain format.");
    } finally {
      setAddingCustomWebsite(false);
    }
  }

  function resetRuleForm() {
    setNewLimit("30");
    setSelectedWebsiteIds([]);
    setWebsiteSearch("");
    setCustomDomain("");
    setCustomLabel("");
    setScopeMode("category");
    setShowNewRule(false);
    setRuleError(null);
  }

  async function handleCreateRule(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedStudent) return;
    const minutes = Number(newLimit);
    if (!newLimit || Number.isNaN(minutes) || minutes <= 0) {
      setRuleError("Enter a limit greater than 0 minutes.");
      return;
    }
    if (scopeMode === "websites" && selectedWebsiteIds.length === 0) {
      setRuleError("Select at least one website, or switch to a category limit.");
      return;
    }
    setCreatingRule(true);
    setRuleError(null);
    try {
      if (scopeMode === "websites") {
        const chosen = websiteCatalog.filter((w) => selectedWebsiteIds.includes(w.id));
        const name = chosen.map((w) => w.label).join(" + ") || "Website limit";
        await api.createRule({
          student_id: selectedStudent,
          name,
          scope_type: "website",
          website_ids: selectedWebsiteIds,
          daily_limit_minutes: minutes,
          warning_one_at_minutes: minutes,
          warning_two_after_additional_minutes: Math.max(1, Math.round(minutes * 0.25)),
          block_after_warning_two_seconds: 60,
        });
      } else {
        const label = CATEGORY_OPTIONS.find((c) => c.key === newCategory)?.label || newCategory;
        await api.createRule({
          student_id: selectedStudent,
          name: `${label} limit`,
          scope_type: "category",
          scope_category_key: newCategory,
          daily_limit_minutes: minutes,
          warning_one_at_minutes: minutes,
          warning_two_after_additional_minutes: Math.max(1, Math.round(minutes * 0.25)),
          block_after_warning_two_seconds: 60,
        });
      }
      resetRuleForm();
      await refresh();
    } catch (e: any) {
      setRuleError(e.message || "Could not create rule.");
    } finally {
      setCreatingRule(false);
    }
  }

  function signOut() {
    clearToken();
    router.push("/");
  }

  if (error) {
    return (
      <div className="container">
        <p>{error}</p>
        <button onClick={signOut}>Back to sign in</button>
      </div>
    );
  }

  return (
    <>
      <Header
        active="dashboard"
        right={
          <a onClick={signOut} style={{ cursor: "pointer" }}>
            Sign out
          </a>
        }
      />
      <div className="container">
        <h1>Family overview</h1>

        {familiesLoaded && families.length === 0 ? (
          <div className="card">
            <h2>No family set up yet</h2>
            <p className="muted">
              Create a family from the API directly, or load a self-contained sample family — a
              student, a Chrome extension, two rules, some usage, a warning, and a pending
              request — to see how FocusSentinel works. Sample data is clearly labeled and never
              mixed with a real account's data.
            </p>
            <button onClick={handleLoadDemo} disabled={demoBusy}>
              {demoBusy ? "Loading..." : "Load Demo Family"}
            </button>
          </div>
        ) : (
          <>
            <p className="muted" style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              <span>
                {families[0]?.name || "Your family"} · {students.length} student{students.length === 1 ? "" : "s"}
              </span>
              {isDemoFamily(families[0]?.name) && <span className="badge none">Demo · sample data</span>}
              {isDemoFamily(families[0]?.name) && (
                <span style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
                  <button className="secondary" onClick={handleSimulate} disabled={simBusy || demoBusy}>
                    {simBusy ? "Simulating..." : "Simulate activity"}
                  </button>
                  <button className="secondary" onClick={handleResetDemo} disabled={demoBusy}>
                    {demoBusy ? "Resetting..." : "Reset Demo"}
                  </button>
                </span>
              )}
            </p>

            {simSteps && (
              <div className="card" style={{ borderColor: "var(--accent)" }}>
                <h2>Demo simulation</h2>
                <p className="muted" style={{ fontSize: 13 }}>
                  This just ran real usage through the actual rules engine and warning/restriction
                  pipeline on the demo student's gaming limit — it is not real browser-extension
                  activity.
                </p>
                {simSteps.length === 0 ? (
                  <p className="muted">Already at the end of the sequence — reset the demo to run it again from the start.</p>
                ) : (
                  simSteps.map((s, i) => (
                    <div className="row" key={i}>
                      <span className={`badge ${s.level === "restricted" ? "restricted" : s.level === "warning_two" ? "warning_two" : s.level === "warning_one" ? "warning_one" : "none"}`}>
                        {s.level.replace(/_/g, " ")}
                      </span>
                      <span className="muted" style={{ fontSize: 13 }}>{s.message}</span>
                    </div>
                  ))
                )}
                <p className="muted" style={{ fontSize: 13, marginTop: 8, marginBottom: 0 }}>
                  A new extension request from Alex should now be waiting below for you to approve or deny.
                </p>
              </div>
            )}

            {students.length > 1 && (
              <select value={selectedStudent || ""} onChange={(e) => setSelectedStudent(e.target.value)}>
                {students.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.display_name}
                  </option>
                ))}
              </select>
            )}

        <div className="card">
          <h2>Today's usage</h2>
          {rules.length === 0 ? (
            <p className="muted">No tracked activity yet today.</p>
          ) : (
            rules.map((rule) => {
              const label = ruleDisplayLabel(rule);
              const seconds = usage?.total_seconds_by_rule[rule.id] || 0;
              const minutesUsed = seconds / 60;
              const limit = rule.daily_limit_minutes || 0;
              const remaining = Math.max(0, limit - minutesUsed);
              const percent = limit > 0 ? Math.min(100, Math.round((minutesUsed / limit) * 100)) : 0;
              const status = usageStatusFor(usage, rule.id, percent);
              return (
                <div key={rule.id} style={{ marginBottom: 16 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 4 }}>
                    <strong>{label}</strong>
                    <span className={`badge ${status.cls}`}>{status.text}</span>
                  </div>
                  <p className="muted" style={{ margin: "0 0 6px", fontSize: 13 }}>
                    {Math.round(minutesUsed)} of {limit} minutes used · {Math.round(remaining)} minutes remaining · {percent}%
                  </p>
                  <div
                    role="progressbar"
                    aria-valuenow={percent}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-label={`${label} usage`}
                    style={{ background: "var(--border)", borderRadius: 999, height: 8, overflow: "hidden" }}
                  >
                    <div
                      style={{
                        width: `${percent}%`,
                        height: "100%",
                        borderRadius: 999,
                        background:
                          status.cls === "restricted" ? "#991b1b" : status.cls === "warning_two" ? "#c2410c" : status.cls === "warning_one" ? "#b45309" : "#2563eb",
                        transition: "width 0.3s ease",
                      }}
                    />
                  </div>
                </div>
              );
            })
          )}
        </div>

        <div className="card">
          <h2>Active warnings & restrictions</h2>
          {usage && usage.active_restrictions.length > 0 ? (
            usage.active_restrictions.map((r, i) => (
              <div className="row" key={i}>
                <span>
                  <span className="badge restricted">restricted</span> {r.reason}
                </span>
                <span className="muted">resets {new Date(r.scheduled_reset_at).toLocaleTimeString()}</span>
              </div>
            ))
          ) : usage && usage.active_warnings.length > 0 ? (
            usage.active_warnings.map((w, i) => (
              <div className="row" key={i}>
                <span className={`badge warning_${w.level === 1 ? "one" : "two"}`}>warning {w.level}</span>
              </div>
            ))
          ) : (
            <p className="muted">Nothing to review right now — usage is within today's limits.</p>
          )}
        </div>

        <div className="card">
          <h2>Screen-time rules</h2>
          {rules.length === 0 && <p className="muted">No rules set yet for this student.</p>}
          {rules.map((rule) => (
            <div className="row" key={rule.id}>
              <span>
                {rule.name}
                {rule.websites.length > 0 && (
                  <span className="muted" style={{ display: "block", fontSize: 12 }}>
                    {rule.websites.map((w) => w.label).join(", ")}
                  </span>
                )}
                {!rule.active && <span className="muted"> (inactive)</span>}
              </span>
              <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <input
                  type="number"
                  min={1}
                  value={limitValueFor(rule)}
                  onChange={(e) => setEditLimits((prev) => ({ ...prev, [rule.id]: e.target.value }))}
                  style={{ width: 70, marginBottom: 0 }}
                />
                <span className="muted" style={{ fontSize: 13 }}>min/day</span>
                <button
                  className="secondary"
                  disabled={savingRuleId === rule.id}
                  onClick={() => handleSaveLimit(rule)}
                >
                  {savingRuleId === rule.id ? "Saving..." : "Save"}
                </button>
              </span>
            </div>
          ))}

          {showNewRule ? (
            <form onSubmit={handleCreateRule} style={{ marginTop: 16, borderTop: "1px solid var(--border)", paddingTop: 16 }}>
              <fieldset style={{ border: "none", padding: 0, margin: "0 0 12px" }}>
                <legend className="muted" style={{ fontSize: 13, marginBottom: 4 }}>What should this limit cover?</legend>
                <label style={{ display: "inline-flex", alignItems: "center", gap: 4, marginRight: 16, fontWeight: 400 }}>
                  <input type="radio" checked={scopeMode === "category"} onChange={() => setScopeMode("category")} />
                  A whole category
                </label>
                <label style={{ display: "inline-flex", alignItems: "center", gap: 4, fontWeight: 400 }}>
                  <input type="radio" checked={scopeMode === "websites"} onChange={() => setScopeMode("websites")} />
                  Specific websites
                </label>
              </fieldset>

              {scopeMode === "category" ? (
                <>
                  <label htmlFor="new-rule-category">Category</label>
                  <select id="new-rule-category" value={newCategory} onChange={(e) => setNewCategory(e.target.value)}>
                    {CATEGORY_OPTIONS.map((c) => (
                      <option key={c.key} value={c.key}>
                        {c.label}
                      </option>
                    ))}
                  </select>
                </>
              ) : (
                <div style={{ marginBottom: 12 }}>
                  <label htmlFor="website-search">Websites (search or pick from the list)</label>
                  {selectedWebsiteIds.length > 0 && (
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 8 }}>
                      {websiteCatalog
                        .filter((w) => selectedWebsiteIds.includes(w.id))
                        .map((w) => (
                          <span key={w.id} className="badge none" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                            {w.label}
                            <button
                              type="button"
                              aria-label={`Remove ${w.label}`}
                              onClick={() => setSelectedWebsiteIds((prev) => prev.filter((id) => id !== w.id))}
                              style={{ background: "none", border: "none", cursor: "pointer", padding: 0, lineHeight: 1, color: "inherit" }}
                            >
                              ×
                            </button>
                          </span>
                        ))}
                    </div>
                  )}
                  <input
                    id="website-search"
                    type="text"
                    placeholder="Search TikTok, YouTube Shorts, Instagram Reels..."
                    value={websiteSearch}
                    onChange={(e) => setWebsiteSearch(e.target.value)}
                  />
                  <div
                    role="listbox"
                    aria-label="Website search results"
                    style={{ maxHeight: 160, overflowY: "auto", border: "1px solid var(--border)", borderRadius: 8, marginTop: 6 }}
                  >
                    {websiteCatalog
                      .filter((w) => !selectedWebsiteIds.includes(w.id))
                      .filter((w) => w.label.toLowerCase().includes(websiteSearch.toLowerCase()) || w.domain.includes(websiteSearch.toLowerCase()))
                      .slice(0, 8)
                      .map((w) => (
                        <button
                          key={w.id}
                          type="button"
                          role="option"
                          aria-selected={false}
                          onClick={() => setSelectedWebsiteIds((prev) => [...prev, w.id])}
                          style={{
                            display: "block",
                            width: "100%",
                            textAlign: "left",
                            padding: "6px 10px",
                            background: "none",
                            border: "none",
                            borderBottom: "1px solid var(--border)",
                            cursor: "pointer",
                          }}
                        >
                          {w.label} <span className="muted" style={{ fontSize: 12 }}>{w.domain}{w.url_pattern || ""}</span>
                        </button>
                      ))}
                    {websiteCatalog.length === 0 && (
                      <p className="muted" style={{ fontSize: 13, padding: "6px 10px" }}>Loading website catalog...</p>
                    )}
                  </div>

                  <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
                    <input
                      type="text"
                      placeholder="Custom domain, e.g. khanacademy.org"
                      value={customDomain}
                      onChange={(e) => setCustomDomain(e.target.value)}
                      style={{ flex: "1 1 160px", marginBottom: 0 }}
                      aria-label="Custom domain"
                    />
                    <input
                      type="text"
                      placeholder="Label (optional)"
                      value={customLabel}
                      onChange={(e) => setCustomLabel(e.target.value)}
                      style={{ flex: "1 1 120px", marginBottom: 0 }}
                      aria-label="Custom website label"
                    />
                    <button
                      type="button"
                      className="secondary"
                      disabled={addingCustomWebsite || !customDomain.trim()}
                      onClick={handleAddCustomWebsite}
                    >
                      {addingCustomWebsite ? "Adding..." : "Add domain"}
                    </button>
                  </div>
                </div>
              )}

              <label htmlFor="new-rule-limit">Daily limit (minutes)</label>
              <input id="new-rule-limit" type="number" min={1} value={newLimit} onChange={(e) => setNewLimit(e.target.value)} />
              {ruleError && <p style={{ color: "#991b1b", fontSize: 13 }}>{ruleError}</p>}
              <button type="submit" disabled={creatingRule}>
                {creatingRule ? "Adding..." : "Add rule"}
              </button>
              <button type="button" className="secondary" onClick={resetRuleForm}>
                Cancel
              </button>
            </form>
          ) : (
            <button className="secondary" style={{ marginTop: 12 }} onClick={() => setShowNewRule(true)}>
              + New rule
            </button>
          )}
        </div>

        <div className="card">
          <h2>Pending extension requests</h2>
          {pendingRequests.length === 0 && <p className="muted">No pending requests.</p>}
          {pendingRequests.map((r) => (
            <div className="row" key={r.id}>
              <span>
                {r.requested_minutes} min requested — {r.reason_code.replace(/_/g, " ")}
              </span>
              <span>
                <button onClick={() => handleApprove(r.id, r.requested_minutes)}>Approve</button>
                <button className="secondary" onClick={() => handleDeny(r.id)}>
                  Deny
                </button>
              </span>
            </div>
          ))}
        </div>

        <div className="card">
          <h2>Device health</h2>
          {health.length === 0 && <p className="muted">No devices registered yet.</p>}
          {health.map((d) => (
            <div className="row" key={d.device_id}>
              <span>{d.device_name}</span>
              <span className="muted">
                {d.status === "not_reporting"
                  ? "Hasn't reported recently — check its permissions"
                  : d.status}
              </span>
            </div>
          ))}
        </div>
          </>
        )}
      </div>
    </>
  );
}
