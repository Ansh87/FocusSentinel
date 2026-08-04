"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, clearToken } from "../../lib/api";
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

  const [showNewRule, setShowNewRule] = useState(false);
  const [newCategory, setNewCategory] = useState(CATEGORY_OPTIONS[0].key);
  const [newLimit, setNewLimit] = useState("30");
  const [creatingRule, setCreatingRule] = useState(false);
  const [ruleError, setRuleError] = useState<string | null>(null);

  useEffect(() => {
    api
      .myFamilies()
      .then(async (fams) => {
        setFamilies(fams);
        if (fams.length > 0) {
          const s = await api.listStudents(fams[0].id);
          setStudents(s);
          if (s.length > 0) setSelectedStudent(s[0].id);
        }
      })
      .catch((e) => setError(e.message || "Please sign in again."));
  }, []);

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
        <p className="muted">
          {families[0]?.name || "Your family"} · {students.length} student{students.length === 1 ? "" : "s"}
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
          <h2>Today's usage by category</h2>
          {usage && Object.keys(usage.total_seconds_by_category).length > 0 ? (
            Object.entries(usage.total_seconds_by_category).map(([cat, seconds]) => (
              <div className="row" key={cat}>
                <span>{cat.replace(/_/g, " ")}</span>
                <span>{Math.round(seconds / 60)} min</span>
              </div>
            ))
          ) : (
            <p className="muted">No tracked activity yet today.</p>
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
      </div>
    </>
  );
}
