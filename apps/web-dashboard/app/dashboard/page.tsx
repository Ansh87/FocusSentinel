"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, clearToken, isDemoFamily } from "../../lib/api";
import { Header } from "../../components/Header";

type Student = { id: string; display_name: string; family_id: string };
type TodayUsage = {
  total_seconds_by_category: Record<string, number>;
  active_warnings: { level: number; rule_id: string }[];
  active_restrictions: { rule_id: string; reason: string; scheduled_reset_at: string }[];
};
type Rule = {
  id: string;
  student_id: string;
  name: string;
  scope_type: string;
  scope_category_key: string | null;
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

  const [showNewRule, setShowNewRule] = useState(false);
  const [newCategory, setNewCategory] = useState(CATEGORY_OPTIONS[0].key);
  const [newLimit, setNewLimit] = useState("30");
  const [creatingRule, setCreatingRule] = useState(false);
  const [ruleError, setRuleError] = useState<string | null>(null);

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

  async function handleCreateRule(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedStudent) return;
    const minutes = Number(newLimit);
    if (!newLimit || Number.isNaN(minutes) || minutes <= 0) {
      setRuleError("Enter a limit greater than 0 minutes.");
      return;
    }
    setCreatingRule(true);
    setRuleError(null);
    try {
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
      setNewLimit("30");
      setShowNewRule(false);
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
                <button className="secondary" onClick={handleResetDemo} disabled={demoBusy} style={{ marginLeft: "auto" }}>
                  {demoBusy ? "Resetting..." : "Reset Demo"}
                </button>
              )}
            </p>

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
              const key = rule.scope_category_key;
              const seconds = (key && usage?.total_seconds_by_category[key]) || 0;
              const minutesUsed = seconds / 60;
              const limit = rule.daily_limit_minutes || 0;
              const remaining = Math.max(0, limit - minutesUsed);
              const percent = limit > 0 ? Math.min(100, Math.round((minutesUsed / limit) * 100)) : 0;
              const status = usageStatusFor(usage, rule.id, percent);
              return (
                <div key={rule.id} style={{ marginBottom: 16 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 4 }}>
                    <strong>{key ? categoryLabel(key) : rule.name}</strong>
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
                    aria-label={`${key ? categoryLabel(key) : rule.name} usage`}
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
              <label>Category</label>
              <select value={newCategory} onChange={(e) => setNewCategory(e.target.value)}>
                {CATEGORY_OPTIONS.map((c) => (
                  <option key={c.key} value={c.key}>
                    {c.label}
                  </option>
                ))}
              </select>
              <label>Daily limit (minutes)</label>
              <input type="number" min={1} value={newLimit} onChange={(e) => setNewLimit(e.target.value)} />
              {ruleError && <p style={{ color: "#991b1b", fontSize: 13 }}>{ruleError}</p>}
              <button type="submit" disabled={creatingRule}>
                {creatingRule ? "Adding..." : "Add rule"}
              </button>
              <button type="button" className="secondary" onClick={() => setShowNewRule(false)}>
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
