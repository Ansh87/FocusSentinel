"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, clearToken } from "../../lib/api";
import { useRequireAuth } from "../../lib/useRequireAuth";
import { Header } from "../../components/Header";

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

const REASON_OPTIONS = [
  { key: "friends", label: "Finishing up with friends" },
  { key: "special_event", label: "Special event" },
  { key: "school_related", label: "School-related" },
  { key: "technical_issue", label: "Technical issue" },
  { key: "other", label: "Other" },
];

function categoryLabel(key: string) {
  return CATEGORY_OPTIONS.find((c) => c.key === key)?.label || key.replace(/_/g, " ");
}

function ruleDisplayLabel(rule: any) {
  if (rule.websites && rule.websites.length > 0) return rule.websites.map((w: any) => w.label).join(" + ");
  if (rule.scope_category_key) return categoryLabel(rule.scope_category_key);
  return rule.name;
}

export default function StudentPage() {
  const router = useRouter();
  const authOk = useRequireAuth();
  const [student, setStudent] = useState<{ id: string; display_name: string; family_id: string; is_sibling_manager?: boolean; sibling_manager_until?: string | null } | null>(null);
  const [usage, setUsage] = useState<any | null>(null);
  const [rules, setRules] = useState<any[]>([]);
  const [requests, setRequests] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  const [siblings, setSiblings] = useState<{ id: string; display_name: string }[]>([]);
  const [manageTarget, setManageTarget] = useState<string | null>(null);
  const [manageRules, setManageRules] = useState<any[]>([]);
  const [manageRequests, setManageRequests] = useState<any[]>([]);
  const [manageBusy, setManageBusy] = useState(false);
  const [manageError, setManageError] = useState<string | null>(null);
  const [editingRuleId, setEditingRuleId] = useState<string | null>(null);
  const [limitDraft, setLimitDraft] = useState("");

  const [reasonCode, setReasonCode] = useState(REASON_OPTIONS[0].key);
  const [ruleId, setRuleId] = useState("");
  const [minutes, setMinutes] = useState("15");
  const [explanation, setExplanation] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);

  function signOut() {
    clearToken();
    router.push("/");
  }

  async function refresh(studentId: string) {
    try {
      const [u, r, reqs] = await Promise.all([api.usageToday(studentId), api.listRules(studentId), api.listExtensionRequests(studentId)]);
      setUsage(u);
      setRules(r);
      setRequests(reqs);
    } catch (e: any) {
      setError(e.message);
    }
  }

  useEffect(() => {
    api
      .myStudentProfile()
      .then(async (s) => {
        setStudent(s);
        await refresh(s.id);
        if (s.is_sibling_manager) {
          const all = await api.listStudents(s.family_id);
          const others = all.filter((sib: any) => sib.id !== s.id);
          setSiblings(others);
          if (others.length > 0) setManageTarget(others[0].id);
        }
      })
      .catch((e: any) => setError(e.message || "No student profile is linked to this account."))
      .finally(() => setLoaded(true));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function refreshManageTarget() {
    if (!manageTarget) return;
    setManageBusy(true);
    setManageError(null);
    try {
      const [r, reqs] = await Promise.all([api.listRules(manageTarget), api.listExtensionRequests(manageTarget, "pending")]);
      setManageRules(r);
      setManageRequests(reqs);
    } catch (e: any) {
      setManageError(e.message || "Could not load this sibling's data.");
    } finally {
      setManageBusy(false);
    }
  }

  useEffect(() => {
    if (!manageTarget) return;
    refreshManageTarget();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [manageTarget]);

  async function handleSaveLimit(ruleId: string) {
    const minutes = Number(limitDraft);
    if (!minutes || minutes <= 0) return;
    setManageBusy(true);
    try {
      await api.updateRule(ruleId, { daily_limit_minutes: minutes });
      setEditingRuleId(null);
      await refreshManageTarget();
    } catch (e: any) {
      setManageError(e.message || "Could not update this rule.");
    } finally {
      setManageBusy(false);
    }
  }

  async function handleManageApprove(id: string, minutes?: number) {
    setManageBusy(true);
    try {
      await api.approveExtension(id, minutes);
      await refreshManageTarget();
    } catch (e: any) {
      setManageError(e.message || "Could not approve this request.");
    } finally {
      setManageBusy(false);
    }
  }

  async function handleManageDeny(id: string) {
    setManageBusy(true);
    try {
      await api.denyExtension(id);
      await refreshManageTarget();
    } catch (e: any) {
      setManageError(e.message || "Could not deny this request.");
    } finally {
      setManageBusy(false);
    }
  }

  useEffect(() => {
    if (!student) return;
    const interval = setInterval(() => refresh(student.id), 10_000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [student]);

  async function handleSubmitRequest(e: React.FormEvent) {
    e.preventDefault();
    if (!student) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      await api.requestExtension({
        student_id: student.id,
        rule_id: ruleId || undefined,
        requested_minutes: minutes ? Number(minutes) : undefined,
        reason_code: reasonCode,
        explanation: explanation || undefined,
      });
      setSubmitted(true);
      setExplanation("");
      await refresh(student.id);
    } catch (e: any) {
      setSubmitError(e.message || "Could not send your request.");
    } finally {
      setSubmitting(false);
    }
  }

  if (!authOk) return null;

  if (loaded && !student) {
    return (
      <>
        <Header
          right={
            <button type="button" className="link-button" onClick={signOut}>
              Sign out
            </button>
          }
        />
        <div className="container">
          <p>{error || "No student profile is linked to this account."}</p>
          <button onClick={signOut}>Back to sign in</button>
        </div>
      </>
    );
  }

  return (
    <>
      <Header
        right={
          <>
            <a href="/account">Account</a>
            <button type="button" className="link-button" onClick={signOut}>
              Sign out
            </button>
          </>
        }
      />
      <div className="container">
        <h1>{student ? `Hi ${student.display_name}` : "Loading..."}</h1>
        <p className="muted">Your screen-time limits and usage for today.</p>

        <div className="card">
          <h2>Today's usage</h2>
          {rules.length === 0 ? (
            <p className="muted">No limits have been set for you yet.</p>
          ) : (
            rules.map((rule) => {
              const label = ruleDisplayLabel(rule);
              const seconds = usage?.total_seconds_by_rule?.[rule.id] || 0;
              const minutesUsed = seconds / 60;
              const limit = rule.daily_limit_minutes || 0;
              const remaining = Math.max(0, limit - minutesUsed);
              const percent = limit > 0 ? Math.min(100, Math.round((minutesUsed / limit) * 100)) : 0;
              const restricted = usage?.active_restrictions?.some((r: any) => r.rule_id === rule.id);
              const warnTwo = usage?.active_warnings?.some((w: any) => w.rule_id === rule.id && w.level === 2);
              const warnOne = usage?.active_warnings?.some((w: any) => w.rule_id === rule.id && w.level === 1);
              const statusCls = restricted ? "restricted" : warnTwo ? "warning_two" : warnOne ? "warning_one" : percent >= 80 ? "progress_notice" : "none";
              const statusText = restricted ? "Restricted" : warnTwo ? "Final warning" : warnOne ? "First warning" : percent >= 80 ? "Almost there" : "Within limit";
              return (
                <div key={rule.id} style={{ marginBottom: 16 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 4 }}>
                    <strong>{label}</strong>
                    <span className={`badge ${statusCls}`}>{statusText}</span>
                  </div>
                  <p className="muted" style={{ margin: "0 0 6px", fontSize: 13 }}>
                    {Math.round(minutesUsed)} of {limit} minutes used · {Math.round(remaining)} minutes remaining
                  </p>
                  <div role="progressbar" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100} aria-label={`${label} usage`} style={{ background: "var(--border)", borderRadius: 999, height: 8, overflow: "hidden" }}>
                    <div
                      style={{
                        width: `${percent}%`,
                        height: "100%",
                        borderRadius: 999,
                        background: statusCls === "restricted" ? "#991b1b" : statusCls === "warning_two" ? "#c2410c" : statusCls === "warning_one" ? "#b45309" : "#2563eb",
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
          <h2>Ask for more time</h2>
          {submitted && (
            <p className="muted" style={{ fontSize: 13, color: "#166534" }}>
              Sent — your parent will see this on their dashboard.
            </p>
          )}
          <form onSubmit={handleSubmitRequest}>
            {rules.length > 0 && (
              <>
                <label htmlFor="req-rule">Which limit?</label>
                <select id="req-rule" value={ruleId} onChange={(e) => setRuleId(e.target.value)}>
                  <option value="">Not sure / general request</option>
                  {rules.map((r) => (
                    <option key={r.id} value={r.id}>
                      {ruleDisplayLabel(r)}
                    </option>
                  ))}
                </select>
              </>
            )}
            <label htmlFor="req-minutes">How many extra minutes?</label>
            <input id="req-minutes" type="number" min={1} value={minutes} onChange={(e) => setMinutes(e.target.value)} />
            <label htmlFor="req-reason">Reason</label>
            <select id="req-reason" value={reasonCode} onChange={(e) => setReasonCode(e.target.value)}>
              {REASON_OPTIONS.map((r) => (
                <option key={r.key} value={r.key}>
                  {r.label}
                </option>
              ))}
            </select>
            <label htmlFor="req-explanation">Tell your parent why (optional)</label>
            <textarea id="req-explanation" value={explanation} onChange={(e) => setExplanation(e.target.value)} rows={3} />
            {submitError && <p style={{ color: "#991b1b", fontSize: 13 }}>{submitError}</p>}
            <button type="submit" disabled={submitting}>
              {submitting ? "Sending..." : "Send request"}
            </button>
          </form>
        </div>

        <div className="card">
          <h2>Your requests</h2>
          {requests.length === 0 && <p className="muted">No requests yet.</p>}
          {requests.map((r) => (
            <div className="row" key={r.id}>
              <span>
                {r.requested_minutes ? `${r.requested_minutes} min` : "Request"} — {r.reason_code.replace(/_/g, " ")}
              </span>
              <span
                className={`badge ${r.status === "approved" ? "none" : r.status === "denied" ? "restricted" : "warning_one"}`}
              >
                {r.status}
              </span>
            </div>
          ))}
        </div>

        {student?.is_sibling_manager && siblings.length > 0 && (
          <div className="card">
            <h2>Manage your siblings</h2>
            <p className="muted" style={{ fontSize: 13, marginTop: -6 }}>
              Your parent gave you permission to adjust limits and decide time requests for the rest of the family
              {student.sibling_manager_until
                ? ` until ${new Date(student.sibling_manager_until).toLocaleString()}.`
                : " — this doesn't expire until they remove it."}
            </p>
            <label htmlFor="manage-target">Sibling</label>
            <select id="manage-target" value={manageTarget || ""} onChange={(e) => setManageTarget(e.target.value)}>
              {siblings.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.display_name}
                </option>
              ))}
            </select>

            {manageError && <p style={{ color: "#991b1b", fontSize: 13 }}>{manageError}</p>}

            <p style={{ fontSize: 13, fontWeight: 600, margin: "14px 0 4px" }}>Pending requests</p>
            {manageRequests.length === 0 ? (
              <p className="muted" style={{ fontSize: 13 }}>Nothing pending.</p>
            ) : (
              manageRequests.map((r) => (
                <div className="row" key={r.id}>
                  <span style={{ fontSize: 13 }}>
                    {r.requested_minutes ? `${r.requested_minutes} min` : "Request"} — {r.reason_code.replace(/_/g, " ")}
                  </span>
                  <span style={{ display: "flex", gap: 6 }}>
                    <button style={{ fontSize: 12, padding: "5px 10px" }} disabled={manageBusy} onClick={() => handleManageApprove(r.id, r.requested_minutes || undefined)}>
                      Approve
                    </button>
                    <button className="secondary" style={{ fontSize: 12, padding: "5px 10px" }} disabled={manageBusy} onClick={() => handleManageDeny(r.id)}>
                      Deny
                    </button>
                  </span>
                </div>
              ))
            )}

            <p style={{ fontSize: 13, fontWeight: 600, margin: "14px 0 4px" }}>Limits</p>
            {manageRules.length === 0 ? (
              <p className="muted" style={{ fontSize: 13 }}>No rules set for this sibling yet.</p>
            ) : (
              manageRules.map((r) => (
                <div className="row" key={r.id}>
                  <span style={{ fontSize: 13 }}>{ruleDisplayLabel(r)}</span>
                  {editingRuleId === r.id ? (
                    <span style={{ display: "flex", gap: 6, alignItems: "center" }}>
                      <input
                        type="number"
                        min={1}
                        value={limitDraft}
                        onChange={(e) => setLimitDraft(e.target.value)}
                        style={{ width: 70, margin: 0, padding: "4px 6px" }}
                      />
                      <button style={{ fontSize: 12, padding: "5px 10px" }} disabled={manageBusy} onClick={() => handleSaveLimit(r.id)}>
                        Save
                      </button>
                      <button className="secondary" style={{ fontSize: 12, padding: "5px 10px" }} onClick={() => setEditingRuleId(null)}>
                        Cancel
                      </button>
                    </span>
                  ) : (
                    <span style={{ display: "flex", gap: 6, alignItems: "center" }}>
                      <span className="muted" style={{ fontSize: 13 }}>{r.daily_limit_minutes ?? "—"} min/day</span>
                      <button
                        className="secondary"
                        style={{ fontSize: 12, padding: "5px 10px" }}
                        onClick={() => {
                          setEditingRuleId(r.id);
                          setLimitDraft(String(r.daily_limit_minutes || ""));
                        }}
                      >
                        Edit
                      </button>
                    </span>
                  )}
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </>
  );
}
