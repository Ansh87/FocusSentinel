"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, clearToken, isDemoAccountEmail, isDemoFamily } from "../../lib/api";
import { useRequireAuth } from "../../lib/useRequireAuth";
import { Header } from "../../components/Header";

type Student = {
  id: string;
  display_name: string;
  family_id: string;
  age_range: string;
  is_sibling_manager?: boolean;
  sibling_manager_until?: string | null;
  is_archived?: boolean;
  has_phone?: boolean;
};
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
  warning_two_after_additional_minutes: number | null;
  block_after_warning_two_seconds: number | null;
  days_of_week: number[] | null;
  reset_time: string | null;
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

const AGE_RANGES = [
  { key: "under_8", label: "Under 8" },
  { key: "8_12", label: "8–12" },
  { key: "13_15", label: "13–15" },
  { key: "16_17", label: "16–17" },
  { key: "18_plus", label: "18+" },
];

const DAYS = [
  { key: 0, label: "Mon" },
  { key: 1, label: "Tue" },
  { key: 2, label: "Wed" },
  { key: 3, label: "Thu" },
  { key: 4, label: "Fri" },
  { key: 5, label: "Sat" },
  { key: 6, label: "Sun" },
];

const EXTENSION_PRESETS = [10, 15, 30];

function categoryLabel(key: string) {
  return CATEGORY_OPTIONS.find((c) => c.key === key)?.label || key.replace(/_/g, " ");
}

function ruleDisplayLabel(rule: Rule) {
  if (rule.websites.length > 0) return rule.websites.map((w) => w.label).join(" + ");
  if (rule.scope_category_key) return categoryLabel(rule.scope_category_key);
  return rule.name;
}

function ruleSitesLine(rule: Rule) {
  if (rule.websites.length > 0) return rule.websites.map((w) => w.label).join(", ");
  if (rule.scope_category_key) return categoryLabel(rule.scope_category_key);
  return "";
}

function relativeTime(iso: string | null | undefined) {
  if (!iso) return "unknown";
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.round(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} minute${mins === 1 ? "" : "s"} ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.round(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

function deviceStatusFor(status: string): { text: string; cls: string; needsAttention: boolean } {
  switch (status) {
    case "connected":
      return { text: "Connected", cls: "connected", needsAttention: false };
    case "delayed":
      return { text: "Delayed", cls: "delayed", needsAttention: true };
    case "offline":
      return { text: "Offline", cls: "offline", needsAttention: true };
    case "permission_issue":
      return { text: "Permission Issue", cls: "permission_issue", needsAttention: true };
    case "revoked":
      return { text: "Revoked", cls: "revoked", needsAttention: true };
    default:
      return { text: status, cls: "none", needsAttention: false };
  }
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

type RuleModalState = {
  mode: "create" | "edit";
  ruleId?: string;
  studentId: string;
  name: string;
  scopeMode: "category" | "websites";
  category: string;
  websiteIds: string[];
  limit: string;
  warningOne: string;
  warningTwoAfter: string;
  blockAfterSeconds: string;
  daysOfWeek: number[];
  resetTime: string;
};

function conflictingRules(state: RuleModalState, existingRules: Rule[]): Rule[] {
  // Two rules covering the same website (or the same category) for the same
  // student would double-count usage against both limits and leave it
  // ambiguous which warning/restriction actually applies -- flag it before
  // save rather than let it happen silently.
  return existingRules.filter((r) => {
    if (r.id === state.ruleId) return false;
    if (r.student_id !== state.studentId) return false;
    if (!r.active) return false;
    if (state.scopeMode === "category") {
      return !!state.category && r.scope_category_key === state.category;
    }
    if (state.websiteIds.length === 0) return false;
    return r.websites.some((w) => state.websiteIds.includes(w.id));
  });
}

function RuleFormModal({
  state,
  setState,
  students,
  websiteCatalog,
  existingRules,
  onAddCustomWebsite,
  onSubmit,
  onClose,
  onDelete,
  busy,
  error,
}: {
  state: RuleModalState;
  setState: (updater: (prev: RuleModalState) => RuleModalState) => void;
  students: Student[];
  websiteCatalog: Website[];
  existingRules: Rule[];
  onAddCustomWebsite: (domain: string, label: string) => Promise<Website | null>;
  onSubmit: () => void;
  onClose: () => void;
  onDelete?: () => void;
  busy: boolean;
  error: string | null;
}) {
  const [websiteSearch, setWebsiteSearch] = useState("");
  const [customDomain, setCustomDomain] = useState("");
  const [customLabel, setCustomLabel] = useState("");
  const [addingCustom, setAddingCustom] = useState(false);
  const conflicts = conflictingRules(state, existingRules);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function handleAddCustom() {
    if (!customDomain.trim()) return;
    setAddingCustom(true);
    try {
      const site = await onAddCustomWebsite(customDomain.trim(), customLabel.trim() || customDomain.trim());
      if (site) {
        setState((prev) => (prev.websiteIds.includes(site.id) ? prev : { ...prev, websiteIds: [...prev.websiteIds, site.id] }));
        setCustomDomain("");
        setCustomLabel("");
      }
    } finally {
      setAddingCustom(false);
    }
  }

  return (
    <div role="presentation" className="modal-backdrop" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="rule-modal-title"
        onClick={(e) => e.stopPropagation()}
        className="card modal-body"
      >
        <h2 id="rule-modal-title">{state.mode === "create" ? "New screen-time rule" : "Edit rule"}</h2>

        <label htmlFor="rule-name">Rule name</label>
        <input id="rule-name" value={state.name} onChange={(e) => setState((p) => ({ ...p, name: e.target.value }))} placeholder="e.g. Short-form video limit" />

        {students.length > 1 && (
          <>
            <label htmlFor="rule-student">Student</label>
            <select id="rule-student" value={state.studentId} onChange={(e) => setState((p) => ({ ...p, studentId: e.target.value }))}>
              {students.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.display_name}
                </option>
              ))}
            </select>
          </>
        )}

        <fieldset style={{ border: "none", padding: 0, margin: "8px 0 12px" }}>
          <legend className="muted" style={{ fontSize: 13, marginBottom: 4 }}>
            What should this limit cover?
          </legend>
          <label style={{ display: "inline-flex", alignItems: "center", gap: 4, marginRight: 16, fontWeight: 400 }}>
            <input type="radio" checked={state.scopeMode === "category"} onChange={() => setState((p) => ({ ...p, scopeMode: "category" }))} />
            A whole category
          </label>
          <label style={{ display: "inline-flex", alignItems: "center", gap: 4, fontWeight: 400 }}>
            <input type="radio" checked={state.scopeMode === "websites"} onChange={() => setState((p) => ({ ...p, scopeMode: "websites" }))} />
            Specific websites
          </label>
        </fieldset>

        {state.scopeMode === "category" ? (
          <>
            <label htmlFor="rule-category">Category</label>
            <select id="rule-category" value={state.category} onChange={(e) => setState((p) => ({ ...p, category: e.target.value }))}>
              {CATEGORY_OPTIONS.map((c) => (
                <option key={c.key} value={c.key}>
                  {c.label}
                </option>
              ))}
            </select>
          </>
        ) : (
          <div style={{ marginBottom: 12 }}>
            <label htmlFor="rule-website-search">Websites</label>
            {state.websiteIds.length > 0 && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 8 }}>
                {websiteCatalog
                  .filter((w) => state.websiteIds.includes(w.id))
                  .map((w) => (
                    <span key={w.id} className="badge none" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                      {w.label}
                      <button
                        type="button"
                        aria-label={`Remove ${w.label}`}
                        onClick={() => setState((p) => ({ ...p, websiteIds: p.websiteIds.filter((id) => id !== w.id) }))}
                        style={{ background: "none", border: "none", cursor: "pointer", padding: 0, color: "inherit" }}
                      >
                        ×
                      </button>
                    </span>
                  ))}
              </div>
            )}
            <input
              id="rule-website-search"
              placeholder="Search TikTok, YouTube Shorts, Instagram Reels..."
              value={websiteSearch}
              onChange={(e) => setWebsiteSearch(e.target.value)}
            />
            <div
              role="listbox"
              aria-label="Website search results"
              style={{ maxHeight: 140, overflowY: "auto", border: "1px solid var(--border)", borderRadius: 8, marginTop: 6 }}
            >
              {websiteCatalog
                .filter((w) => !state.websiteIds.includes(w.id))
                .filter((w) => w.label.toLowerCase().includes(websiteSearch.toLowerCase()) || w.domain.includes(websiteSearch.toLowerCase()))
                .slice(0, 8)
                .map((w) => (
                  <button
                    key={w.id}
                    type="button"
                    role="option"
                    aria-selected={false}
                    onClick={() => setState((p) => ({ ...p, websiteIds: [...p.websiteIds, w.id] }))}
                    style={{
                      display: "block",
                      width: "100%",
                      textAlign: "left",
                      padding: "6px 10px",
                      background: "none",
                      color: "var(--ink)",
                      whiteSpace: "normal",
                      border: "none",
                      borderBottom: "1px solid var(--border)",
                      cursor: "pointer",
                    }}
                  >
                    {w.label} <span className="muted" style={{ fontSize: 12 }}>{w.domain}{w.url_pattern || ""}</span>
                  </button>
                ))}
              {websiteCatalog.length === 0 && (
                <p className="muted" style={{ fontSize: 13, padding: "6px 10px" }}>
                  Loading website catalog...
                </p>
              )}
            </div>
            <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
              <input
                placeholder="Custom domain"
                value={customDomain}
                onChange={(e) => setCustomDomain(e.target.value)}
                style={{ flex: "1 1 140px", marginBottom: 0 }}
                aria-label="Custom domain"
              />
              <input
                placeholder="Label (optional)"
                value={customLabel}
                onChange={(e) => setCustomLabel(e.target.value)}
                style={{ flex: "1 1 120px", marginBottom: 0 }}
                aria-label="Custom website label"
              />
              <button type="button" className="secondary" disabled={addingCustom || !customDomain.trim()} onClick={handleAddCustom}>
                {addingCustom ? "Adding..." : "Add domain"}
              </button>
            </div>
          </div>
        )}

        <label htmlFor="rule-limit">Daily limit (minutes)</label>
        <input id="rule-limit" type="number" min={1} value={state.limit} onChange={(e) => setState((p) => ({ ...p, limit: e.target.value }))} />

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <div style={{ flex: "1 1 130px" }}>
            <label htmlFor="rule-warn1">First warning at (min)</label>
            <input id="rule-warn1" type="number" min={1} value={state.warningOne} onChange={(e) => setState((p) => ({ ...p, warningOne: e.target.value }))} />
          </div>
          <div style={{ flex: "1 1 130px" }}>
            <label htmlFor="rule-warn2">2nd warning after (+min)</label>
            <input id="rule-warn2" type="number" min={0} value={state.warningTwoAfter} onChange={(e) => setState((p) => ({ ...p, warningTwoAfter: e.target.value }))} />
          </div>
          <div style={{ flex: "1 1 130px" }}>
            <label htmlFor="rule-grace">Grace period (sec)</label>
            <input id="rule-grace" type="number" min={0} value={state.blockAfterSeconds} onChange={(e) => setState((p) => ({ ...p, blockAfterSeconds: e.target.value }))} />
          </div>
        </div>

        <label>Active days</label>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 10 }}>
          {DAYS.map((d) => {
            const on = state.daysOfWeek.includes(d.key);
            return (
              <button
                key={d.key}
                type="button"
                className={on ? "" : "secondary"}
                style={{ padding: "4px 10px", fontSize: 12, marginLeft: 0 }}
                onClick={() =>
                  setState((p) => ({
                    ...p,
                    daysOfWeek: on ? p.daysOfWeek.filter((x) => x !== d.key) : [...p.daysOfWeek, d.key],
                  }))
                }
              >
                {d.label}
              </button>
            );
          })}
        </div>

        <label htmlFor="rule-reset">Resets at</label>
        <input id="rule-reset" type="time" value={state.resetTime} onChange={(e) => setState((p) => ({ ...p, resetTime: e.target.value }))} />

        {conflicts.length > 0 && (
          <p style={{ color: "#92400e", fontSize: 13, background: "#fffbeb", border: "1px solid #fde68a", borderRadius: 8, padding: "8px 10px" }}>
            This overlaps with "{conflicts.map((r) => r.name).join(", ")}" for the same student. Usage would count
            against both limits, and it won't be clear which one applies — consider adjusting one of them.
          </p>
        )}

        {error && <p style={{ color: "#991b1b", fontSize: 13 }}>{error}</p>}

        <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap", alignItems: "center" }}>
          <button type="button" onClick={onSubmit} disabled={busy}>
            {busy ? "Saving..." : state.mode === "create" ? "Add rule" : "Save changes"}
          </button>
          <button type="button" className="secondary" onClick={onClose}>
            Cancel
          </button>
          {state.mode === "edit" && onDelete && (
            <button type="button" className="danger" style={{ marginLeft: "auto" }} onClick={onDelete}>
              Delete
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const router = useRouter();
  const authOk = useRequireAuth();
  const [families, setFamilies] = useState<{ id: string; name: string }[]>([]);
  const [students, setStudents] = useState<Student[]>([]);
  const [selectedView, setSelectedView] = useState<string>("");
  const focusedStudentId = selectedView && selectedView !== "all" ? selectedView : null;
  const focusedStudent = students.find((s) => s.id === focusedStudentId) || null;
  // Archived students stay visible (and reversible) in "Manage students" but
  // drop out of the Viewing selector, the "all students" summary, and the
  // student picker inside the rule form -- archiving is meant to get someone
  // out of the way without losing their history the way a hard delete would.
  const activeStudents = students.filter((s) => !s.is_archived);

  const [usage, setUsage] = useState<TodayUsage | null>(null);
  const [pendingRequests, setPendingRequests] = useState<any[]>([]);
  const [health, setHealth] = useState<any[]>([]);
  const [rules, setRules] = useState<Rule[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [familiesLoaded, setFamiliesLoaded] = useState(false);
  const [demoBusy, setDemoBusy] = useState(false);
  const [simSteps, setSimSteps] = useState<any[] | null>(null);
  const [simBusy, setSimBusy] = useState(false);

  const [websiteCatalog, setWebsiteCatalog] = useState<Website[]>([]);

  const [ruleModal, setRuleModal] = useState<RuleModalState | null>(null);
  const [ruleModalBusy, setRuleModalBusy] = useState(false);
  const [ruleModalError, setRuleModalError] = useState<string | null>(null);

  const [troubleshootDevice, setTroubleshootDevice] = useState<any | null>(null);
  const [registeringDevice, setRegisteringDevice] = useState(false);
  const [newDeviceName, setNewDeviceName] = useState("");
  const [deviceTokenModal, setDeviceTokenModal] = useState<{ name: string; token: string } | null>(null);

  const [customAmounts, setCustomAmounts] = useState<Record<string, string>>({});
  const [allowMoreTimeFor, setAllowMoreTimeFor] = useState<string | null>(null);

  const [setupStatus, setSetupStatus] = useState<any | null>(null);
  const [reminderHidden, setReminderHidden] = useState(false);

  const [allSummary, setAllSummary] = useState<Record<string, { restricted: boolean; rulesCount: number }>>({});
  const [allSummaryLoading, setAllSummaryLoading] = useState(false);

  const [studentLoginStatus, setStudentLoginStatus] = useState<{ has_login: boolean; email: string | null } | null>(null);
  const [showStudentLoginForm, setShowStudentLoginForm] = useState(false);
  const [studentLoginEmail, setStudentLoginEmail] = useState("");
  const [studentLoginPassword, setStudentLoginPassword] = useState("");
  const [studentLoginBusy, setStudentLoginBusy] = useState(false);
  const [studentLoginError, setStudentLoginError] = useState<string | null>(null);

  const [parentName, setParentName] = useState<string | null>(null);
  const [parentEmail, setParentEmail] = useState<string | null>(null);
  const isDemoAccount = isDemoAccountEmail(parentEmail);
  // Actions (Simulate/Reset/delete/etc.) get their own dismissible banner --
  // separate from `error`, which stays reserved for "we couldn't load your
  // account at all" and replaces the whole page. A single failed button
  // click shouldn't wipe out the dashboard and imply the session expired.
  const [actionError, setActionError] = useState<string | null>(null);

  const [showAddStudent, setShowAddStudent] = useState(false);
  const [addStudentName, setAddStudentName] = useState("");
  const [addStudentAge, setAddStudentAge] = useState(AGE_RANGES[2].key);
  const [addStudentBusy, setAddStudentBusy] = useState(false);
  const [addStudentError, setAddStudentError] = useState<string | null>(null);

  const [editingStudentId, setEditingStudentId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editAge, setEditAge] = useState(AGE_RANGES[2].key);
  const [editPhone, setEditPhone] = useState("");
  const [editBusy, setEditBusy] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [archiveBusyId, setArchiveBusyId] = useState<string | null>(null);

  const [smsStatus, setSmsStatus] = useState<{ enabled: boolean; phone_number: string | null } | null>(null);

  const [deleteStudentTarget, setDeleteStudentTarget] = useState<Student | null>(null);
  const [deleteStudentBusy, setDeleteStudentBusy] = useState(false);
  const [clearHistoryBusy, setClearHistoryBusy] = useState(false);
  const [clearHistoryDone, setClearHistoryDone] = useState(false);
  const [siblingManagerBusy, setSiblingManagerBusy] = useState(false);
  const [siblingManagerDuration, setSiblingManagerDuration] = useState<Record<string, string>>({});

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setTroubleshootDevice(null);
        setDeviceTokenModal(null);
        setSimSteps(null);
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  async function loadFamilies() {
    try {
      const allFams = await api.myFamilies();
      // Defensive: an older build let "Explore with sample data" attach a
      // demo family directly to a real account (fixed now -- see /demo/load
      // server-side guard), so any account that isn't the reserved public
      // demo login should never treat a leftover demo-named family as its
      // primary one. Real families are preferred whenever both exist.
      const realFams = allFams.filter((f: { name: string }) => !isDemoFamily(f.name));
      const fams = realFams.length > 0 ? realFams : allFams;
      setFamilies(fams);
      if (fams.length > 0) {
        const s = await api.listStudents(fams[0].id);
        setStudents(s);
        // With exactly one kid there's nothing to choose -- go straight to their
        // usage. With more than one, default to the "All students" chooser so a
        // parent explicitly picks who they're looking at, rather than silently
        // landing on whichever student happened to load first.
        const activeNow = s.filter((st: Student) => !st.is_archived);
        if (activeNow.length > 0) {
          setSelectedView((prev) => {
            if (prev === "all" || (prev && activeNow.some((st: Student) => st.id === prev))) return prev;
            return activeNow.length === 1 ? activeNow[0].id : "all";
          });
        } else {
          setSelectedView("");
        }
      } else {
        setStudents([]);
        setSelectedView("");
      }
    } catch (e: any) {
      setError(e.message || "Please sign in again.");
    } finally {
      setFamiliesLoaded(true);
    }
  }

  useEffect(() => {
    loadFamilies();
    api
      .me()
      .then((u) => {
        setParentName(u.display_name);
        setParentEmail(u.email);
      })
      .catch(() => {
        /* non-fatal -- greeting just won't show a name */
      });
    api
      .getSmsStatus()
      .then(setSmsStatus)
      .catch(() => {
        /* non-fatal -- text-to-request explainer just won't show */
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleAddStudent(e: React.FormEvent) {
    e.preventDefault();
    if (!addStudentName.trim() || !families[0]?.id) return;
    setAddStudentBusy(true);
    setAddStudentError(null);
    try {
      const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
      await api.createStudent(families[0].id, addStudentName.trim(), addStudentAge, tz);
      setAddStudentName("");
      setShowAddStudent(false);
      await loadFamilies();
    } catch (e: any) {
      setAddStudentError(e.message || "Could not add this student.");
    } finally {
      setAddStudentBusy(false);
    }
  }

  async function handleDeleteStudent() {
    if (!deleteStudentTarget) return;
    setDeleteStudentBusy(true);
    try {
      await api.deleteStudent(deleteStudentTarget.id);
      setDeleteStudentTarget(null);
      if (selectedView === deleteStudentTarget.id) setSelectedView("");
      await loadFamilies();
    } catch (e: any) {
      setActionError(e.message || "Could not delete this student.");
    } finally {
      setDeleteStudentBusy(false);
    }
  }

  async function startEditStudent(s: Student) {
    setEditingStudentId(s.id);
    setEditName(s.display_name);
    setEditAge(s.age_range || AGE_RANGES[2].key);
    setEditPhone("");
    setEditError(null);
    if (s.has_phone) {
      try {
        const status = await api.getStudentPhone(s.id);
        setEditPhone(status.phone_number || "");
      } catch {
        /* non-fatal -- phone field just starts blank */
      }
    }
  }

  async function handleSaveEditStudent() {
    if (!editingStudentId || !editName.trim()) return;
    setEditBusy(true);
    setEditError(null);
    try {
      await api.updateStudent(editingStudentId, { display_name: editName.trim(), age_range: editAge });
      if (editPhone.trim()) {
        await api.setStudentPhone(editingStudentId, editPhone.trim());
      } else {
        await api.clearStudentPhone(editingStudentId);
      }
      setEditingStudentId(null);
      await loadFamilies();
    } catch (e: any) {
      setEditError(e.message || "Could not save these changes.");
    } finally {
      setEditBusy(false);
    }
  }

  async function handleToggleArchive(s: Student) {
    setArchiveBusyId(s.id);
    try {
      if (s.is_archived) {
        await api.unarchiveStudent(s.id);
      } else {
        await api.archiveStudent(s.id);
      }
      await loadFamilies();
    } catch (e: any) {
      setActionError(e.message || "Could not update this student's archive status.");
    } finally {
      setArchiveBusyId(null);
    }
  }

  async function handleClearHistory() {
    if (!focusedStudentId) return;
    if (!window.confirm(`Clear all recorded activity history for ${focusedStudent?.display_name || "this student"}? This can't be undone.`)) return;
    setClearHistoryBusy(true);
    setClearHistoryDone(false);
    try {
      await api.clearUsageHistory(focusedStudentId);
      setClearHistoryDone(true);
      await refresh();
    } catch (e: any) {
      setActionError(e.message || "Could not clear activity history.");
    } finally {
      setClearHistoryBusy(false);
    }
  }

  async function handleToggleSiblingManager(student: Student) {
    setSiblingManagerBusy(true);
    try {
      if (student.is_sibling_manager) {
        await api.revokeSiblingManager(student.id);
      } else {
        const hoursStr = siblingManagerDuration[student.id] ?? "24";
        await api.grantSiblingManager(student.id, hoursStr ? Number(hoursStr) : null);
      }
      await loadFamilies();
    } catch (e: any) {
      setActionError(e.message || "Could not update sibling-manager permission.");
    } finally {
      setSiblingManagerBusy(false);
    }
  }

  useEffect(() => {
    if (!families[0]?.id) return;
    api
      .websitesCatalog(families[0].id)
      .then(setWebsiteCatalog)
      .catch(() => {
        /* non-fatal -- the website multi-select just won't have options yet */
      });
  }, [families]);

  async function handleResetDemo() {
    setDemoBusy(true);
    setSimSteps(null);
    try {
      await api.resetDemo();
      await loadFamilies();
      await refresh();
    } catch (e: any) {
      setActionError(e.message || "Could not reset demo data.");
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
      setActionError(e.message || "Could not run the simulation.");
    } finally {
      setSimBusy(false);
    }
  }

  useEffect(() => {
    if (!families[0]?.id) {
      setSetupStatus(null);
      return;
    }
    api
      .getSetupStatus(families[0].id)
      .then(setSetupStatus)
      .catch(() => {
        /* non-fatal -- the setup banner just won't show */
      });
  }, [families, students, rules]);

  async function handleDismissReminder() {
    if (!families[0]?.id) return;
    setReminderHidden(true);
    try {
      const status = await api.dismissSetupReminder(families[0].id);
      setSetupStatus(status);
    } catch {
      /* the banner already hid locally either way */
    }
  }

  useEffect(() => {
    if (!focusedStudentId) return;
    refresh();
    const interval = setInterval(refresh, 10_000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusedStudentId]);

  useEffect(() => {
    setShowStudentLoginForm(false);
    setStudentLoginError(null);
    if (!focusedStudentId) {
      setStudentLoginStatus(null);
      return;
    }
    api
      .getStudentLoginStatus(focusedStudentId)
      .then((status) => {
        setStudentLoginStatus(status);
        setStudentLoginEmail(status.email || "");
      })
      .catch(() => setStudentLoginStatus(null));
  }, [focusedStudentId]);

  async function handleSetStudentLogin(e: React.FormEvent) {
    e.preventDefault();
    if (!focusedStudentId) return;
    setStudentLoginBusy(true);
    setStudentLoginError(null);
    try {
      const status = await api.setStudentLogin(focusedStudentId, studentLoginEmail, studentLoginPassword);
      setStudentLoginStatus(status);
      setStudentLoginPassword("");
      setShowStudentLoginForm(false);
    } catch (e: any) {
      setStudentLoginError(e.message || "Could not save this login.");
    } finally {
      setStudentLoginBusy(false);
    }
  }

  useEffect(() => {
    if (students.length === 0) return;
    setAllSummaryLoading(true);
    Promise.all(
      students.map(async (s) => {
        try {
          const [u, r] = await Promise.all([api.usageToday(s.id), api.listRules(s.id)]);
          return [s.id, { restricted: (u.active_restrictions || []).length > 0, rulesCount: r.length }] as const;
        } catch {
          return [s.id, { restricted: false, rulesCount: 0 }] as const;
        }
      })
    )
      .then((entries) => setAllSummary(Object.fromEntries(entries)))
      .finally(() => setAllSummaryLoading(false));
  }, [students]);

  async function refresh() {
    if (!focusedStudentId) return;
    try {
      const [u, reqs, h, r] = await Promise.all([
        api.usageToday(focusedStudentId),
        api.listExtensionRequests(focusedStudentId, "pending"),
        api.deviceHealth(focusedStudentId),
        api.listRules(focusedStudentId),
      ]);
      setUsage(u);
      setPendingRequests(reqs);
      setHealth(h);
      setRules(r);
    } catch (e: any) {
      setActionError(e.message);
    }
  }

  function scrollToUsage() {
    document.getElementById("today-usage")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function handleApprove(id: string, minutes: number) {
    await api.approveExtension(id, minutes);
    refresh();
  }

  async function handleDeny(id: string) {
    await api.denyExtension(id);
    refresh();
  }

  async function handleAllowMoreTime(ruleId: string, minutes: number) {
    if (!focusedStudentId) return;
    try {
      await api.grantExtension(focusedStudentId, ruleId, minutes);
      setAllowMoreTimeFor(null);
      await refresh();
    } catch (e: any) {
      setActionError(e.message);
    }
  }

  async function handleTogglePause(rule: Rule) {
    try {
      await api.updateRule(rule.id, { active: !rule.active });
      await refresh();
    } catch (e: any) {
      setActionError(e.message);
    }
  }

  async function handleDeleteRule(rule: Rule) {
    if (!window.confirm(`Delete "${rule.name}"? This can't be undone.`)) return;
    try {
      await api.deleteRule(rule.id);
      await refresh();
    } catch (e: any) {
      setActionError(e.message);
    }
  }

  async function handleRegisterDevice() {
    if (!focusedStudentId || !newDeviceName.trim()) return;
    try {
      const result = await api.registerDevice({ student_id: focusedStudentId, device_type: "browser_extension", name: newDeviceName.trim() });
      setDeviceTokenModal({ name: newDeviceName.trim(), token: result.device_token });
      setNewDeviceName("");
      setRegisteringDevice(false);
      await refresh();
    } catch (e: any) {
      setActionError(e.message);
    }
  }

  async function handleAddCustomWebsiteGlobal(domain: string, label: string): Promise<Website | null> {
    if (!families[0]?.id) return null;
    try {
      const site: Website = await api.addWebsite({ family_id: families[0].id, domain, label, category_key: "other" });
      setWebsiteCatalog((prev) => (prev.some((w) => w.id === site.id) ? prev : [...prev, site]));
      return site;
    } catch (e: any) {
      setRuleModalError(e.message || "Could not add that website — check the domain format.");
      return null;
    }
  }

  function openNewRule() {
    if (!focusedStudentId) return;
    setRuleModalError(null);
    setRuleModal({
      mode: "create",
      studentId: focusedStudentId,
      name: "",
      scopeMode: "category",
      category: CATEGORY_OPTIONS[0].key,
      websiteIds: [],
      limit: "30",
      warningOne: "24",
      warningTwoAfter: "3",
      blockAfterSeconds: "60",
      daysOfWeek: [0, 1, 2, 3, 4, 5, 6],
      resetTime: "00:00",
    });
  }

  function openEditRule(rule: Rule) {
    setRuleModalError(null);
    setRuleModal({
      mode: "edit",
      ruleId: rule.id,
      studentId: rule.student_id,
      name: rule.name,
      scopeMode: rule.websites.length > 0 ? "websites" : "category",
      category: rule.scope_category_key || CATEGORY_OPTIONS[0].key,
      websiteIds: rule.websites.map((w) => w.id),
      limit: String(rule.daily_limit_minutes ?? ""),
      warningOne: String(rule.warning_one_at_minutes ?? ""),
      warningTwoAfter: String(rule.warning_two_after_additional_minutes ?? 5),
      blockAfterSeconds: String(rule.block_after_warning_two_seconds ?? 60),
      daysOfWeek: rule.days_of_week && rule.days_of_week.length ? rule.days_of_week : [0, 1, 2, 3, 4, 5, 6],
      resetTime: rule.reset_time || "00:00",
    });
  }

  async function handleSubmitRuleModal() {
    if (!ruleModal) return;
    const limit = Number(ruleModal.limit);
    const warnOne = Number(ruleModal.warningOne);
    if (!ruleModal.limit || Number.isNaN(limit) || limit <= 0) {
      setRuleModalError("Enter a limit greater than 0 minutes.");
      return;
    }
    if (ruleModal.scopeMode === "websites" && ruleModal.websiteIds.length === 0) {
      setRuleModalError("Select at least one website, or switch to a category limit.");
      return;
    }
    setRuleModalBusy(true);
    setRuleModalError(null);
    try {
      const payload: Record<string, unknown> = {
        name:
          ruleModal.name.trim() ||
          (ruleModal.scopeMode === "category"
            ? `${CATEGORY_OPTIONS.find((c) => c.key === ruleModal.category)?.label || ruleModal.category} limit`
            : "Website limit"),
        daily_limit_minutes: limit,
        warning_one_at_minutes: warnOne || limit,
        warning_two_after_additional_minutes: Number(ruleModal.warningTwoAfter) || 1,
        block_after_warning_two_seconds: Number(ruleModal.blockAfterSeconds) || 60,
        days_of_week: ruleModal.daysOfWeek,
        reset_time: ruleModal.resetTime,
        student_id: ruleModal.studentId,
      };
      if (ruleModal.scopeMode === "category") {
        payload.scope_category_key = ruleModal.category;
      } else {
        payload.website_ids = ruleModal.websiteIds;
      }

      if (ruleModal.mode === "create") {
        payload.scope_type = ruleModal.scopeMode === "category" ? "category" : "website";
        await api.createRule(payload);
      } else if (ruleModal.ruleId) {
        await api.updateRule(ruleModal.ruleId, payload);
      }
      setRuleModal(null);
      await refresh();
    } catch (e: any) {
      setRuleModalError(e.message || "Could not save this rule.");
    } finally {
      setRuleModalBusy(false);
    }
  }

  async function handleDeleteFromModal() {
    if (!ruleModal?.ruleId) return;
    if (!window.confirm(`Delete "${ruleModal.name || "this rule"}"? This can't be undone.`)) return;
    setRuleModalBusy(true);
    try {
      await api.deleteRule(ruleModal.ruleId);
      setRuleModal(null);
      await refresh();
    } catch (e: any) {
      setRuleModalError(e.message);
    } finally {
      setRuleModalBusy(false);
    }
  }

  function signOut() {
    clearToken();
    router.push("/");
  }

  if (!authOk) return null;

  if (error) {
    return (
      <div className="container">
        <p>{error}</p>
        <button onClick={signOut}>Back to sign in</button>
      </div>
    );
  }

  const setupReminderDismissed =
    reminderHidden ||
    !!(setupStatus?.reminder_dismissed_until && new Date(setupStatus.reminder_dismissed_until) > new Date());

  return (
    <>
      <Header
        active="dashboard"
        right={
          <>
            <a href="/dashboard/activity">Activity</a>
            {setupStatus && !setupStatus.is_complete && <a href="/setup">Complete Setup</a>}
            <a href="/account">Account</a>
            <button type="button" className="link-button" onClick={signOut}>
              Sign out
            </button>
          </>
        }
      />
      <div className="container-wide">
        <h1>{parentName ? `Hi ${parentName} — Family overview` : "Family overview"}</h1>

        {actionError && (
          <p
            className="card"
            style={{ borderColor: "#fca5a5", background: "#fef2f2", color: "#991b1b", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, fontSize: 14 }}
          >
            <span>{actionError}</span>
            <button type="button" className="link-button" style={{ color: "#991b1b" }} onClick={() => setActionError(null)}>
              Dismiss
            </button>
          </p>
        )}

        {familiesLoaded && families.length === 0 ? (
          <div className="card">
            <h2>Welcome to FocusSentinel</h2>
            <p className="muted">
              Let's set up your family's digital-wellbeing plan. A short guided setup walks you through your family
              profile, your first student, the websites you want to manage, and your first screen-time rule.
            </p>
            <button onClick={() => router.push("/setup")}>Start guided setup</button>
            <div style={{ borderTop: "1px solid var(--border)", marginTop: 16, paddingTop: 16 }}>
              <a
                href="/"
                target="_blank"
                rel="noopener noreferrer"
                className="secondary"
                style={{ display: "inline-block", padding: "8px 14px", borderRadius: 8, border: "1px solid var(--border)", textDecoration: "none", color: "var(--ink)" }}
              >
                Explore Sample Dashboard ↗
              </a>
              <p className="muted" style={{ fontSize: 12, marginTop: 6 }}>
                Opens the public interactive demo in a new tab, signed into a completely separate sample account -- it
                never touches your own
                family's data.
              </p>
            </div>
          </div>
        ) : (
          <>
            {setupStatus && !setupStatus.is_complete && !setupReminderDismissed && (
              <div className="card" style={{ borderColor: "var(--accent)" }}>
                <h2>Complete your FocusSentinel setup</h2>
                <p className="muted" style={{ marginTop: -6 }}>
                  You've completed {setupStatus.completed_steps} of {setupStatus.total_steps} steps.
                </p>
                {setupStatus.remaining_steps.length > 0 && (
                  <ul style={{ margin: "0 0 12px", paddingLeft: 20, fontSize: 14 }}>
                    {setupStatus.remaining_steps.map((s: string) => (
                      <li key={s}>{s}</li>
                    ))}
                  </ul>
                )}
                <div style={{ display: "flex", gap: 8 }}>
                  <button onClick={() => router.push("/setup")}>Continue Setup</button>
                  <button className="secondary" onClick={handleDismissReminder}>
                    Remind Me Later
                  </button>
                </div>
              </div>
            )}

            <p className="muted" style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              <span>
                {families[0]?.name || "Your family"} · {activeStudents.length} student{activeStudents.length === 1 ? "" : "s"}
              </span>
              {isDemoAccount && <span className="badge none">Demo · sample data</span>}
              {setupStatus && !setupStatus.is_complete && setupReminderDismissed && (
                <button
                  type="button"
                  className="link-button"
                  onClick={() => router.push("/setup")}
                  style={{ fontSize: 13, color: "var(--warn)" }}
                >
                  Setup incomplete · {setupStatus.completed_steps} of {setupStatus.total_steps} steps
                </button>
              )}
              {isDemoAccount && (
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

            {activeStudents.length > 0 && (
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
                <label htmlFor="student-select" style={{ margin: 0, whiteSpace: "nowrap" }}>
                  Viewing
                </label>
                <select id="student-select" value={selectedView} onChange={(e) => setSelectedView(e.target.value)} style={{ width: "auto", marginBottom: 0 }}>
                  {activeStudents.length > 1 && <option value="all">All students</option>}
                  {activeStudents.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.display_name}
                    </option>
                  ))}
                </select>
                {focusedStudentId && (
                  <>
                    <span className="muted" style={{ fontSize: 13 }}>
                      Everything below reflects this student.
                    </span>
                    <button
                      className="secondary"
                      style={{ fontSize: 12, padding: "5px 10px", marginLeft: "auto" }}
                      disabled={clearHistoryBusy}
                      onClick={handleClearHistory}
                    >
                      {clearHistoryBusy ? "Clearing..." : "Clear activity history"}
                    </button>
                  </>
                )}
              </div>
            )}
            {clearHistoryDone && (
              <p className="muted" style={{ fontSize: 13, color: "#166534", marginTop: -8 }}>
                Activity history cleared.
              </p>
            )}

            {/* Always reachable, regardless of which student (if any) is currently
                focused above -- adding or removing a student, or handing a sibling
                management access, shouldn't require first landing on the "All
                students" view. */}
            <div className="card">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 8 }}>
                <h2 style={{ marginBottom: 0 }}>Manage students</h2>
                <button className="secondary" onClick={() => setShowAddStudent((v) => !v)} style={{ fontSize: 13, padding: "6px 12px" }}>
                  {showAddStudent ? "Cancel" : "+ Add a student"}
                </button>
              </div>
              <p className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                Archiving hides a student from the dashboard and rule creation without deleting their history — reverse
                it anytime with Unarchive. Delete removes them and their history permanently.
              </p>
              {smsStatus?.enabled ? (
                <p className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                  Add a student's phone number below (click Edit) to let them text{" "}
                  <strong>{smsStatus.phone_number}</strong> to request more time — you'll get a text back to approve
                  or deny with a simple reply, no need to open the dashboard.
                </p>
              ) : (
                <p className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                  Texting to request time isn't turned on for this deployment yet (needs a Twilio number configured
                  server-side). You can still save a student's phone number now — it'll start working once that's
                  set up.
                </p>
              )}
              {showAddStudent && (
                <form onSubmit={handleAddStudent} style={{ margin: "12px 0", padding: 12, background: "var(--accent-soft)", borderRadius: 10 }}>
                  <label htmlFor="add-student-name">Student's name</label>
                  <input id="add-student-name" value={addStudentName} onChange={(e) => setAddStudentName(e.target.value)} required />
                  <label htmlFor="add-student-age">Age range</label>
                  <select id="add-student-age" value={addStudentAge} onChange={(e) => setAddStudentAge(e.target.value)}>
                    {AGE_RANGES.map((a) => (
                      <option key={a.key} value={a.key}>
                        {a.label}
                      </option>
                    ))}
                  </select>
                  {addStudentError && <p style={{ color: "#991b1b", fontSize: 13 }}>{addStudentError}</p>}
                  <button type="submit" disabled={addStudentBusy}>
                    {addStudentBusy ? "Adding..." : "Add student"}
                  </button>
                </form>
              )}
              {students.length === 0 && <p className="muted">No students yet — add your first one above.</p>}
              {allSummaryLoading && <p className="muted">Loading...</p>}
              {students.map((s) => (
                <div key={s.id} style={{ borderBottom: "1px solid var(--border)", padding: "8px 0" }}>
                  {editingStudentId === s.id ? (
                    <div style={{ padding: 12, background: "var(--accent-soft)", borderRadius: 10 }}>
                      <label htmlFor={`edit-name-${s.id}`}>Name</label>
                      <input id={`edit-name-${s.id}`} value={editName} onChange={(e) => setEditName(e.target.value)} />
                      <label htmlFor={`edit-age-${s.id}`}>Age range</label>
                      <select id={`edit-age-${s.id}`} value={editAge} onChange={(e) => setEditAge(e.target.value)}>
                        {AGE_RANGES.map((a) => (
                          <option key={a.key} value={a.key}>
                            {a.label}
                          </option>
                        ))}
                      </select>
                      <label htmlFor={`edit-phone-${s.id}`}>
                        Phone number {smsStatus?.enabled ? "(to text for more time)" : ""}
                      </label>
                      <input
                        id={`edit-phone-${s.id}`}
                        type="tel"
                        placeholder="(555) 123-4567"
                        value={editPhone}
                        onChange={(e) => setEditPhone(e.target.value)}
                      />
                      <p className="muted" style={{ fontSize: 12, marginTop: -8 }}>
                        {smsStatus?.enabled
                          ? `Once set, ${s.display_name} can text ${smsStatus.phone_number} to ask for more time. Leave blank to remove.`
                          : "Saved even before texting is turned on for this deployment -- leave blank to remove."}
                      </p>
                      {editError && <p style={{ color: "#991b1b", fontSize: 13 }}>{editError}</p>}
                      <div style={{ display: "flex", gap: 8 }}>
                        <button onClick={handleSaveEditStudent} disabled={editBusy || !editName.trim()}>
                          {editBusy ? "Saving..." : "Save"}
                        </button>
                        <button className="secondary" onClick={() => setEditingStudentId(null)} disabled={editBusy}>
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="row" style={{ borderBottom: "none", padding: 0 }}>
                      <span>
                        {s.display_name}
                        {s.is_archived && (
                          <span className="badge none" style={{ marginLeft: 8, fontSize: 11 }}>
                            Archived
                          </span>
                        )}
                        {s.is_sibling_manager && (
                          <span className="badge none" style={{ marginLeft: 8, fontSize: 11 }}>
                            Manages siblings{s.sibling_manager_until ? ` until ${new Date(s.sibling_manager_until).toLocaleString()}` : ""}
                          </span>
                        )}
                        {s.has_phone ? (
                          <span className="badge none" style={{ marginLeft: 8, fontSize: 11 }}>
                            Can text for time
                          </span>
                        ) : (
                          !s.is_archived && (
                            <button
                              type="button"
                              className="link-button"
                              style={{ marginLeft: 8, fontSize: 11 }}
                              onClick={() => startEditStudent(s)}
                            >
                              + Add phone to text for time
                            </button>
                          )
                        )}
                      </span>
                      <span style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                        <span className="muted" style={{ fontSize: 13 }}>
                          {allSummary[s.id]?.rulesCount ?? 0} rule{(allSummary[s.id]?.rulesCount ?? 0) === 1 ? "" : "s"}
                          {allSummary[s.id]?.restricted ? " · restricted" : ""}
                        </span>
                        {!s.is_archived && (
                          <button className="secondary" onClick={() => setSelectedView(s.id)} style={{ fontSize: 13, padding: "6px 10px" }}>
                            View
                          </button>
                        )}
                        <button className="secondary" onClick={() => startEditStudent(s)} style={{ fontSize: 13, padding: "6px 10px" }}>
                          Edit
                        </button>
                        {!s.is_archived && activeStudents.length > 1 && (
                          <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                            {s.is_sibling_manager ? (
                              <button
                                className="secondary"
                                disabled={siblingManagerBusy}
                                onClick={() => handleToggleSiblingManager(s)}
                                style={{ fontSize: 13, padding: "6px 10px" }}
                              >
                                Remove manage access
                              </button>
                            ) : (
                              <>
                                <select
                                  value={siblingManagerDuration[s.id] || "24"}
                                  onChange={(e) => setSiblingManagerDuration((prev) => ({ ...prev, [s.id]: e.target.value }))}
                                  style={{ width: "auto", margin: 0, padding: "4px 6px", fontSize: 12 }}
                                >
                                  <option value="1">1 hour</option>
                                  <option value="24">1 day</option>
                                  <option value="168">1 week</option>
                                  <option value="">Indefinite</option>
                                </select>
                                <button
                                  className="secondary"
                                  disabled={siblingManagerBusy}
                                  onClick={() => handleToggleSiblingManager(s)}
                                  style={{ fontSize: 13, padding: "6px 10px" }}
                                >
                                  Let manage siblings
                                </button>
                              </>
                            )}
                          </span>
                        )}
                        <button
                          className="secondary"
                          disabled={archiveBusyId === s.id}
                          onClick={() => handleToggleArchive(s)}
                          style={{ fontSize: 13, padding: "6px 10px" }}
                        >
                          {archiveBusyId === s.id ? "..." : s.is_archived ? "Unarchive" : "Archive"}
                        </button>
                        <button className="danger" onClick={() => setDeleteStudentTarget(s)} style={{ fontSize: 13, padding: "6px 10px" }}>
                          Delete
                        </button>
                      </span>
                    </div>
                  )}
                </div>
              ))}
              {activeStudents.length > 1 && (
                <p className="muted" style={{ fontSize: 12, marginTop: 10, marginBottom: 0 }}>
                  "Let manage siblings" authorizes that student (they need their own sign-in first) to edit screen-time
                  rules and approve or deny extension requests for the others, for the duration you pick — handy for
                  letting an eldest sibling cover for you temporarily. It never gives them account or billing access.
                </p>
              )}
            </div>

            {selectedView === "all" ? (
              activeStudents.length > 1 && (
                <p className="muted" style={{ fontSize: 13 }}>
                  Pick "View" above for any student to see their usage, rules, and requests.
                </p>
              )
            ) : (
              <div className="dashboard-grid">
                <div className="dashboard-col">
                  <div className="card" id="today-usage">
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
                                    status.cls === "restricted"
                                      ? "#991b1b"
                                      : status.cls === "warning_two"
                                      ? "#c2410c"
                                      : status.cls === "warning_one"
                                      ? "#b45309"
                                      : "#2563eb",
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
                    <h2>Screen-time rules</h2>
                    {rules.length === 0 && (
                      <p className="muted">
                        No screen-time rules yet for {focusedStudent?.display_name || "this student"}. Add one below to
                        start tracking and limiting their time on specific sites or categories.
                      </p>
                    )}
                    {rules.map((rule) => {
                      const sitesLine = ruleSitesLine(rule);
                      return (
                        <div key={rule.id} style={{ padding: "12px 0", borderBottom: "1px solid var(--border)" }}>
                          <strong>
                            {rule.name}
                            {!rule.active && <span className="muted"> (paused)</span>}
                          </strong>
                          {sitesLine && (
                            <p className="muted" style={{ margin: "2px 0", fontSize: 13 }}>
                              {sitesLine}
                            </p>
                          )}
                          <p className="muted" style={{ margin: "2px 0 8px", fontSize: 13 }}>
                            {rule.daily_limit_minutes} minutes {rule.websites.length > 1 ? "combined " : ""}per day
                          </p>
                          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                            <button className="secondary" onClick={() => openEditRule(rule)}>
                              Edit
                            </button>
                            <button className="secondary" onClick={() => handleTogglePause(rule)}>
                              {rule.active ? "Pause" : "Resume"}
                            </button>
                            <button className="danger" onClick={() => handleDeleteRule(rule)}>
                              Delete
                            </button>
                          </div>
                        </div>
                      );
                    })}
                    <button className="secondary" style={{ marginTop: 12 }} onClick={openNewRule}>
                      + New rule
                    </button>
                  </div>
                </div>

                <div className="dashboard-col">
                  <div className="card">
                    <h2>Active warnings & restrictions</h2>
                    {usage && usage.active_restrictions.length > 0 ? (
                      usage.active_restrictions.map((r, i) => {
                        const rule = rules.find((ru) => ru.id === r.rule_id);
                        const label = rule ? ruleDisplayLabel(rule) : "Limit";
                        const seconds = usage?.total_seconds_by_rule[r.rule_id] || 0;
                        const minutesUsed = Math.round(seconds / 60);
                        const limit = rule?.daily_limit_minutes || 0;
                        const studentName = focusedStudent?.display_name || "Your student";
                        return (
                          <div key={i} style={{ padding: "10px 0", borderBottom: "1px solid var(--border)" }}>
                            <strong>{label} reached</strong>
                            <p className="muted" style={{ margin: "4px 0", fontSize: 13 }}>
                              {studentName} used {minutesUsed} of {limit} minutes. {r.reason}
                            </p>
                            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                              <button className="secondary" onClick={() => setAllowMoreTimeFor(allowMoreTimeFor === r.rule_id ? null : r.rule_id)}>
                                Allow more time
                              </button>
                              <button className="secondary" onClick={scrollToUsage}>
                                View activity
                              </button>
                            </div>
                            {allowMoreTimeFor === r.rule_id && (
                              <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
                                {EXTENSION_PRESETS.map((m) => (
                                  <button key={m} className="secondary" onClick={() => handleAllowMoreTime(r.rule_id, m)}>
                                    +{m} min
                                  </button>
                                ))}
                              </div>
                            )}
                          </div>
                        );
                      })
                    ) : usage && usage.active_warnings.length > 0 ? (
                      usage.active_warnings.map((w, i) => {
                        const rule = rules.find((ru) => ru.id === w.rule_id);
                        return (
                          <div className="row" key={i}>
                            <span className={`badge warning_${w.level === 1 ? "one" : "two"}`}>warning {w.level}</span>
                            <span className="muted">{rule ? ruleDisplayLabel(rule) : ""}</span>
                          </div>
                        );
                      })
                    ) : (
                      <p className="muted">Nothing to review right now — usage is within today's limits.</p>
                    )}
                  </div>

                  <div className="card">
                    <h2>Pending extension requests</h2>
                    {smsStatus?.enabled && pendingRequests.length > 0 && (
                      <p className="muted" style={{ fontSize: 12, marginTop: -6 }}>
                        If this came in by text, you can also reply YES or NO to that text instead of using the
                        buttons below.
                      </p>
                    )}
                    {pendingRequests.length === 0 && <p className="muted">No pending requests.</p>}
                    {pendingRequests.map((r) => {
                      const rule = rules.find((ru) => ru.id === r.rule_id);
                      const websiteLabel = rule?.websites?.[0]?.label;
                      const studentName = focusedStudent?.display_name || "Your student";
                      const custom = customAmounts[r.id] || "";
                      return (
                        <div key={r.id} style={{ padding: "10px 0", borderBottom: "1px solid var(--border)" }}>
                          <strong>
                            {studentName} requested {r.requested_minutes ?? ""} additional minutes
                          </strong>
                          {rule && (
                            <p className="muted" style={{ margin: "2px 0", fontSize: 13 }}>
                              Rule: {ruleDisplayLabel(rule)}
                            </p>
                          )}
                          {websiteLabel && (
                            <p className="muted" style={{ margin: "2px 0", fontSize: 13 }}>
                              Website: {websiteLabel}
                            </p>
                          )}
                          {r.explanation && (
                            <p className="muted" style={{ margin: "2px 0", fontSize: 13 }}>
                              Reason: "{r.explanation}"
                            </p>
                          )}
                          <p className="muted" style={{ margin: "2px 0 8px", fontSize: 12 }}>
                            Requested {relativeTime(r.created_at)}
                          </p>
                          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                            {EXTENSION_PRESETS.map((m) => (
                              <button key={m} className="secondary" onClick={() => handleApprove(r.id, m)}>
                                Approve {m} min
                              </button>
                            ))}
                            <input
                              type="number"
                              min={1}
                              placeholder="Custom"
                              value={custom}
                              onChange={(e) => setCustomAmounts((prev) => ({ ...prev, [r.id]: e.target.value }))}
                              style={{ width: 80, marginBottom: 0 }}
                              aria-label="Custom approve amount"
                            />
                            <button
                              className="secondary"
                              disabled={!custom}
                              onClick={() => {
                                handleApprove(r.id, Number(custom));
                                setCustomAmounts((prev) => ({ ...prev, [r.id]: "" }));
                              }}
                            >
                              Approve custom
                            </button>
                            <button className="danger" onClick={() => handleDeny(r.id)}>
                              Deny
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  <div className="card">
                    <h2>Device health</h2>
                    {health.map((d) => {
                      const st = deviceStatusFor(d.status);
                      return (
                        <div key={d.device_id} style={{ padding: "10px 0", borderBottom: "1px solid var(--border)" }}>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
                            <span>{d.device_name}</span>
                            <span className={`badge ${st.cls}`}>{st.text}</span>
                          </div>
                          <p className="muted" style={{ fontSize: 12, margin: "4px 0 0" }}>
                            {d.last_seen_at ? `Last synchronized: ${relativeTime(d.last_seen_at)}` : "Never synchronized"}
                            {d.platform_identifier ? ` · Browser: ${d.platform_identifier}` : ""}
                          </p>
                          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                            {st.needsAttention && (
                              <button className="secondary" onClick={() => setTroubleshootDevice(d)}>
                                Troubleshoot
                              </button>
                            )}
                            <button className="secondary" onClick={() => setTroubleshootDevice(d)}>
                              View permissions
                            </button>
                          </div>
                        </div>
                      );
                    })}
                    {health.length === 0 && (
                      <div>
                        <p className="muted">No devices registered yet.</p>
                        {!registeringDevice ? (
                          <button className="secondary" onClick={() => setRegisteringDevice(true)}>
                            Connect a device
                          </button>
                        ) : (
                          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                            <input
                              placeholder="Device name, e.g. Alex's Chrome"
                              value={newDeviceName}
                              onChange={(e) => setNewDeviceName(e.target.value)}
                              style={{ flex: "1 1 200px", marginBottom: 0 }}
                            />
                            <button onClick={handleRegisterDevice} disabled={!newDeviceName.trim()}>
                              Register
                            </button>
                            <button className="secondary" onClick={() => setRegisteringDevice(false)}>
                              Cancel
                            </button>
                          </div>
                        )}
                      </div>
                    )}
                  </div>

                  <div className="card">
                    <h2>Student sign-in</h2>
                    {studentLoginStatus?.has_login ? (
                      <p className="muted" style={{ fontSize: 13 }}>
                        {focusedStudent?.display_name} can sign in with <strong>{studentLoginStatus.email}</strong> to view their own
                        usage and request more time.
                      </p>
                    ) : (
                      <p className="muted" style={{ fontSize: 13 }}>
                        {focusedStudent?.display_name} doesn't have a login yet — they can only be seen through this dashboard.
                      </p>
                    )}
                    {!showStudentLoginForm ? (
                      <button className="secondary" onClick={() => setShowStudentLoginForm(true)}>
                        {studentLoginStatus?.has_login ? "Reset password" : "Create login"}
                      </button>
                    ) : (
                      <form onSubmit={handleSetStudentLogin}>
                        <label htmlFor="student-login-email">Email</label>
                        <input
                          id="student-login-email"
                          type="email"
                          required
                          value={studentLoginEmail}
                          onChange={(e) => setStudentLoginEmail(e.target.value)}
                        />
                        <label htmlFor="student-login-password">Password</label>
                        <input
                          id="student-login-password"
                          type="password"
                          required
                          minLength={8}
                          value={studentLoginPassword}
                          onChange={(e) => setStudentLoginPassword(e.target.value)}
                        />
                        {studentLoginError && <p style={{ color: "#991b1b", fontSize: 13 }}>{studentLoginError}</p>}
                        <button type="submit" disabled={studentLoginBusy}>
                          {studentLoginBusy ? "Saving..." : "Save login"}
                        </button>
                        <button type="button" className="secondary" onClick={() => setShowStudentLoginForm(false)}>
                          Cancel
                        </button>
                      </form>
                    )}
                  </div>
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {ruleModal && (
        <RuleFormModal
          state={ruleModal}
          setState={(updater) => setRuleModal((prev) => (prev ? updater(prev) : prev))}
          students={activeStudents}
          websiteCatalog={websiteCatalog}
          existingRules={rules}
          onAddCustomWebsite={handleAddCustomWebsiteGlobal}
          onSubmit={handleSubmitRuleModal}
          onClose={() => setRuleModal(null)}
          onDelete={ruleModal.mode === "edit" ? handleDeleteFromModal : undefined}
          busy={ruleModalBusy}
          error={ruleModalError}
        />
      )}

      {simSteps && (
        <div role="presentation" className="modal-backdrop" onClick={() => setSimSteps(null)}>
          <div role="dialog" aria-modal="true" aria-labelledby="sim-modal-title" onClick={(e) => e.stopPropagation()} className="card modal-body">
            <h2 id="sim-modal-title">Demo simulation</h2>
            <p className="muted" style={{ fontSize: 13 }}>
              This ran real usage through the actual rules engine and warning/restriction pipeline on the demo
              student's gaming limit — it is not real browser-extension activity.
            </p>
            {simSteps.length === 0 ? (
              <p className="muted">Already at the end of the sequence — reset the demo to run it again from the start.</p>
            ) : (
              simSteps.map((s, i) => (
                <div className="row" key={i}>
                  <span
                    className={`badge ${
                      s.level === "restricted" ? "restricted" : s.level === "warning_two" ? "warning_two" : s.level === "warning_one" ? "warning_one" : "none"
                    }`}
                  >
                    {s.level.replace(/_/g, " ")}
                  </span>
                  <span className="muted" style={{ fontSize: 13 }}>
                    {s.message}
                  </span>
                </div>
              ))
            )}
            <p className="muted" style={{ fontSize: 13, marginTop: 8 }}>
              A new extension request should now be waiting for you to approve or deny.
            </p>
            <button className="secondary" onClick={() => setSimSteps(null)}>
              Close
            </button>
          </div>
        </div>
      )}

      {deviceTokenModal && (
        <div role="presentation" className="modal-backdrop" onClick={() => setDeviceTokenModal(null)}>
          <div role="dialog" aria-modal="true" aria-labelledby="token-modal-title" onClick={(e) => e.stopPropagation()} className="card modal-body">
            <h2 id="token-modal-title">{deviceTokenModal.name} registered</h2>
            <p className="muted" style={{ fontSize: 13 }}>
              Paste this token into the FocusSentinel browser extension's setup screen on the student's device. It's
              shown only once — if you lose it, register the device again.
            </p>
            <input readOnly value={deviceTokenModal.token} onFocus={(e) => e.currentTarget.select()} style={{ fontFamily: "monospace", fontSize: 13 }} />
            <button className="secondary" onClick={() => setDeviceTokenModal(null)}>
              Close
            </button>
          </div>
        </div>
      )}

      {troubleshootDevice && (
        <div role="presentation" className="modal-backdrop" onClick={() => setTroubleshootDevice(null)}>
          <div role="dialog" aria-modal="true" aria-labelledby="troubleshoot-title" onClick={(e) => e.stopPropagation()} className="card modal-body">
            <h2 id="troubleshoot-title">Troubleshoot {troubleshootDevice.device_name}</h2>
            <p className="muted" style={{ fontSize: 13 }}>
              {troubleshootDevice.status === "revoked"
                ? "This device's access was revoked. Register it again from this student's device to resume tracking."
                : "This device hasn't reported recently, or one of its permissions is off. Try these steps:"}
            </p>
            <ol style={{ paddingLeft: 20, fontSize: 14, color: "var(--ink)" }}>
              <li>Make sure the FocusSentinel browser extension is installed and enabled.</li>
              <li>Open the extension and confirm it shows as connected to this student's account.</li>
              <li>Check that the device has an active internet connection.</li>
              <li>Confirm any browser permission prompts from the extension were accepted.</li>
              <li>If the issue continues, remove and re-register the device from a parent account.</li>
            </ol>
            {Object.keys(troubleshootDevice.permissions || {}).length > 0 && (
              <>
                <p style={{ fontSize: 13, fontWeight: 600, margin: "12px 0 4px" }}>Permissions on file</p>
                <ul style={{ paddingLeft: 20, fontSize: 13, color: "var(--muted)", margin: 0 }}>
                  {Object.entries(troubleshootDevice.permissions).map(([key, granted]) => (
                    <li key={key}>
                      {key.replace(/_/g, " ")}: {granted ? "granted" : "not granted"}
                    </li>
                  ))}
                </ul>
              </>
            )}
            <button className="secondary" style={{ marginTop: 16 }} onClick={() => setTroubleshootDevice(null)}>
              Close
            </button>
          </div>
        </div>
      )}

      {deleteStudentTarget && (
        <div role="presentation" className="modal-backdrop" onClick={() => (!deleteStudentBusy ? setDeleteStudentTarget(null) : null)}>
          <div role="dialog" aria-modal="true" aria-labelledby="delete-student-title" onClick={(e) => e.stopPropagation()} className="card modal-body">
            <h2 id="delete-student-title">Delete {deleteStudentTarget.display_name}?</h2>
            <p className="muted" style={{ fontSize: 13 }}>
              This permanently removes {deleteStudentTarget.display_name}'s profile, screen-time rules, connected
              devices, activity history, and extension request history. Their sign-in (if they have one) is deleted
              too. This can't be undone.
            </p>
            <div style={{ display: "flex", gap: 8 }}>
              <button className="danger" disabled={deleteStudentBusy} onClick={handleDeleteStudent}>
                {deleteStudentBusy ? "Deleting..." : "Delete permanently"}
              </button>
              <button className="secondary" disabled={deleteStudentBusy} onClick={() => setDeleteStudentTarget(null)}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
