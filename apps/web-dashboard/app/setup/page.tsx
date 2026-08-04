"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "../../lib/api";
import { useRequireAuth } from "../../lib/useRequireAuth";
import { Header } from "../../components/Header";

type Website = {
  id: string;
  domain: string;
  url_pattern: string | null;
  label: string;
  category_id: string | null;
  source: string;
  is_custom: boolean;
};

type Student = { id: string; display_name: string; family_id: string };

const AGE_RANGES = [
  { key: "under_8", label: "Under 8" },
  { key: "8_12", label: "8–12" },
  { key: "13_15", label: "13–15" },
  { key: "16_17", label: "16–17" },
  { key: "18_plus", label: "18 or older" },
];

const DAY_PRESETS = [
  { key: "every_day", label: "Every day", days: [0, 1, 2, 3, 4, 5, 6] },
  { key: "weekdays", label: "Weekdays", days: [0, 1, 2, 3, 4] },
  { key: "weekends", label: "Weekends", days: [5, 6] },
];

const STEP_LABELS = ["Family profile", "Add a student", "Choose websites", "Create a rule", "Connect a device"];

function StepProgress({ step }: { step: number }) {
  return (
    <div style={{ marginBottom: 20 }}>
      <p className="muted" style={{ fontSize: 13, margin: "0 0 6px" }}>
        Step {step} of 5 &middot; {STEP_LABELS[step - 1]}
      </p>
      <div style={{ display: "flex", gap: 4 }}>
        {STEP_LABELS.map((label, i) => (
          <div
            key={label}
            style={{
              flex: 1,
              height: 6,
              borderRadius: 999,
              background: i + 1 <= step ? "var(--accent)" : "var(--border)",
            }}
          />
        ))}
      </div>
    </div>
  );
}

export default function SetupWizardPage() {
  const router = useRouter();
  const authOk = useRequireAuth();

  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [step, setStep] = useState(1);

  const [familyId, setFamilyId] = useState<string | null>(null);
  const [familyName, setFamilyName] = useState("");
  const [timezone, setTimezone] = useState("UTC");
  const [parentName, setParentName] = useState("");
  const [parentEmail, setParentEmail] = useState("");
  const [parentMobile, setParentMobile] = useState("");
  const [step1Busy, setStep1Busy] = useState(false);
  const [step1Error, setStep1Error] = useState<string | null>(null);

  const [students, setStudents] = useState<Student[]>([]);
  const [newStudentName, setNewStudentName] = useState("");
  const [newStudentAge, setNewStudentAge] = useState(AGE_RANGES[2].key);
  const [newDeviceLabel, setNewDeviceLabel] = useState("");
  const [step2Busy, setStep2Busy] = useState(false);
  const [step2Error, setStep2Error] = useState<string | null>(null);

  const [websiteCatalog, setWebsiteCatalog] = useState<Website[]>([]);
  const [selectedWebsiteIds, setSelectedWebsiteIds] = useState<string[]>([]);
  const [websiteSearch, setWebsiteSearch] = useState("");
  const [customDomain, setCustomDomain] = useState("");
  const [customLabel, setCustomLabel] = useState("");
  const [customPath, setCustomPath] = useState("");
  const [step3Busy, setStep3Busy] = useState(false);
  const [step3Error, setStep3Error] = useState<string | null>(null);

  const [ruleName, setRuleName] = useState("Short-Form Video Limit");
  const [ruleStudentId, setRuleStudentId] = useState("");
  const [dailyLimit, setDailyLimit] = useState("30");
  const [dayPreset, setDayPreset] = useState(DAY_PRESETS[0].key);
  const [resetTime, setResetTime] = useState("00:00");
  const [ruleCreated, setRuleCreated] = useState<{ id: string } | null>(null);
  const [step4Busy, setStep4Busy] = useState(false);
  const [step4Error, setStep4Error] = useState<string | null>(null);

  const [deviceStudentId, setDeviceStudentId] = useState("");
  const [deviceToken, setDeviceToken] = useState<{ name: string; token: string } | null>(null);
  const [connectionCheck, setConnectionCheck] = useState<string | null>(null);
  const [step5Busy, setStep5Busy] = useState(false);
  const [step5Error, setStep5Error] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const fams = await api.myFamilies();
        const me = await api.me().catch(() => null);
        if (me) setParentEmail(me.email);

        if (fams.length === 0) {
          setTimezone(Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC");
          setLoaded(true);
          return;
        }

        const fam = fams[0];
        setFamilyId(fam.id);
        setFamilyName(fam.name);
        setTimezone(fam.timezone);

        const [s, catalog, status] = await Promise.all([
          api.listStudents(fam.id),
          api.websitesCatalog(fam.id),
          api.getSetupStatus(fam.id),
        ]);
        setStudents(s);
        setWebsiteCatalog(catalog);
        if (s.length > 0) {
          setRuleStudentId(s[0].id);
          setDeviceStudentId(s[0].id);
        }

        // Resume at the first incomplete step, rather than always starting
        // over at step 1 -- this is what makes "Save and finish later"
        // actually pick back up where it left off.
        if (!status.student_added) setStep(2);
        else if (!status.first_rule_created) setStep(3);
        else if (!status.device_connected && !status.device_connect_skipped) setStep(5);
        else setStep(5);
      } catch (e: any) {
        setError(e.message || "Could not load your setup progress.");
      } finally {
        setLoaded(true);
      }
    }
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function finishLater() {
    router.push("/dashboard");
  }

  async function handleStep1Continue(e: React.FormEvent) {
    e.preventDefault();
    if (!familyName.trim()) return;
    setStep1Busy(true);
    setStep1Error(null);
    try {
      if (familyId) {
        await api.updateFamily(familyId, { name: familyName.trim(), timezone });
      } else {
        const fam = await api.createFamily(familyName.trim(), timezone);
        setFamilyId(fam.id);
      }
      // Parent name/email/mobile are collected here for the notification
      // recipient this family will use, but aren't persisted until a rule
      // actually needs someone to notify -- kept as local wizard state and
      // handed to the notification-recipient step naturally via the
      // existing /notification-recipients endpoint would be a reasonable
      // Priority 2 follow-up; for now this step's required output is just
      // the family profile itself.
      setStep(2);
    } catch (e: any) {
      setStep1Error(e.message || "Could not save your family profile.");
    } finally {
      setStep1Busy(false);
    }
  }

  async function handleAddStudent() {
    if (!familyId || !newStudentName.trim()) return;
    setStep2Busy(true);
    setStep2Error(null);
    try {
      const tz = timezone || "UTC";
      const student = await api.createStudent(familyId, newStudentName.trim(), newStudentAge, tz);
      setStudents((prev) => [...prev, student]);
      setRuleStudentId((prev) => prev || student.id);
      setDeviceStudentId((prev) => prev || student.id);
      setNewStudentName("");
      setNewDeviceLabel("");
    } catch (e: any) {
      setStep2Error(e.message || "Could not add this student.");
    } finally {
      setStep2Busy(false);
    }
  }

  async function handleAddCustomWebsite() {
    if (!familyId || !customDomain.trim()) return;
    setStep3Busy(true);
    setStep3Error(null);
    try {
      const site = await api.addWebsite({
        family_id: familyId,
        domain: customDomain.trim(),
        label: customLabel.trim() || customDomain.trim(),
        url_pattern: customPath.trim() ? (customPath.trim().startsWith("/") ? customPath.trim() : `/${customPath.trim()}`) : undefined,
      });
      setWebsiteCatalog((prev) => [...prev, site]);
      setSelectedWebsiteIds((prev) => [...prev, site.id]);
      setCustomDomain("");
      setCustomLabel("");
      setCustomPath("");
    } catch (e: any) {
      setStep3Error(e.message || "Could not add that website. Check the domain and try again.");
    } finally {
      setStep3Busy(false);
    }
  }

  function toggleWebsite(id: string) {
    setSelectedWebsiteIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  async function handleCreateRule() {
    if (!ruleStudentId || selectedWebsiteIds.length === 0) return;
    setStep4Busy(true);
    setStep4Error(null);
    try {
      const limit = Math.max(1, Number(dailyLimit) || 30);
      const warningOne = Math.max(1, Math.round(limit * 0.8));
      const warningTwoAfter = Math.max(0, limit - warningOne);
      const days = DAY_PRESETS.find((d) => d.key === dayPreset)?.days || DAY_PRESETS[0].days;
      const rule = await api.createRule({
        student_id: ruleStudentId,
        name: ruleName.trim() || "Short-Form Video Limit",
        scope_type: "website",
        website_ids: selectedWebsiteIds,
        daily_limit_minutes: limit,
        warning_one_at_minutes: warningOne,
        warning_two_after_additional_minutes: warningTwoAfter,
        block_after_warning_two_seconds: 300,
        days_of_week: days,
        reset_time: resetTime || "00:00",
      });
      setRuleCreated({ id: rule.id });
      setStep(5);
    } catch (e: any) {
      setStep4Error(e.message || "Could not create this rule.");
    } finally {
      setStep4Busy(false);
    }
  }

  async function handleConnectDevice() {
    if (!deviceStudentId) return;
    setStep5Busy(true);
    setStep5Error(null);
    setConnectionCheck(null);
    try {
      const student = students.find((s) => s.id === deviceStudentId);
      const name = newDeviceLabel.trim() || `${student?.display_name || "Student"}'s browser extension`;
      const result = await api.registerDevice({ student_id: deviceStudentId, device_type: "browser_extension", name });
      setDeviceToken({ name, token: result.device_token });
    } catch (e: any) {
      setStep5Error(e.message || "Could not register this device.");
    } finally {
      setStep5Busy(false);
    }
  }

  async function handleTestConnection() {
    if (!deviceStudentId) return;
    setConnectionCheck("Checking...");
    try {
      const health = await api.deviceHealth(deviceStudentId);
      const device = health[health.length - 1];
      if (!device) {
        setConnectionCheck("No device found yet for this student.");
      } else if (device.status === "connected" || device.status === "delayed") {
        setConnectionCheck(`${device.device_name} is reporting in (${device.status}).`);
      } else {
        setConnectionCheck(
          `${device.device_name} hasn't reported in yet. Install the browser extension, paste in the token above, and try again in a moment.`
        );
      }
    } catch (e: any) {
      setConnectionCheck(e.message || "Could not check connection status.");
    }
  }

  async function handleSkipDevice() {
    if (!familyId) return;
    setStep5Busy(true);
    try {
      await api.skipDeviceSetup(familyId);
      router.push("/dashboard");
    } catch (e: any) {
      setStep5Error(e.message || "Could not save that.");
    } finally {
      setStep5Busy(false);
    }
  }

  function handleCompleteSetup() {
    router.push("/dashboard");
  }

  if (!authOk) return null;

  if (error) {
    return (
      <div className="container">
        <p>{error}</p>
        <button onClick={() => router.push("/dashboard")}>Back to dashboard</button>
      </div>
    );
  }

  if (!loaded) {
    return (
      <>
        <Header active="dashboard" />
        <div className="container">
          <p className="muted">Loading...</p>
        </div>
      </>
    );
  }

  const selectedWebsites = websiteCatalog.filter((w) => selectedWebsiteIds.includes(w.id));
  const filteredCatalog = websiteCatalog
    .filter((w) => !selectedWebsiteIds.includes(w.id))
    .filter((w) => w.label.toLowerCase().includes(websiteSearch.toLowerCase()) || w.domain.toLowerCase().includes(websiteSearch.toLowerCase()));

  return (
    <>
      <Header active="dashboard" right={<button type="button" className="link-button" onClick={finishLater}>Save and finish later</button>} />
      <div className="container" style={{ maxWidth: 560 }}>
        {step === 1 && (
          <>
            <h1>Welcome to FocusSentinel</h1>
            <p className="muted">
              Let's set up your family's digital-wellbeing plan. You can complete the setup now or return to it later.
            </p>
          </>
        )}

        <StepProgress step={step} />

        {step === 1 && (
          <form onSubmit={handleStep1Continue} className="card">
            <h2>Family profile</h2>
            <label htmlFor="family-name">Family display name</label>
            <input
              id="family-name"
              value={familyName}
              onChange={(e) => setFamilyName(e.target.value)}
              placeholder="Saini Family"
              required
            />
            <p className="muted" style={{ marginTop: -6, marginBottom: 10, fontSize: 12 }}>
              Your family name appears only inside your FocusSentinel account.
            </p>

            <label htmlFor="family-tz">Timezone</label>
            <input id="family-tz" value={timezone} onChange={(e) => setTimezone(e.target.value)} required />

            <label htmlFor="parent-name">Your name (optional)</label>
            <input id="parent-name" value={parentName} onChange={(e) => setParentName(e.target.value)} />

            <label htmlFor="parent-email">Notification email (optional)</label>
            <input id="parent-email" type="email" value={parentEmail} onChange={(e) => setParentEmail(e.target.value)} />

            <label htmlFor="parent-mobile">Mobile phone (optional)</label>
            <input id="parent-mobile" value={parentMobile} onChange={(e) => setParentMobile(e.target.value)} />

            {step1Error && <p style={{ color: "#991b1b", fontSize: 13 }}>{step1Error}</p>}
            <div style={{ display: "flex", gap: 8 }}>
              <button type="submit" disabled={step1Busy || !familyName.trim()}>
                {step1Busy ? "Saving..." : "Continue"}
              </button>
              <button type="button" className="secondary" onClick={finishLater}>
                Save and finish later
              </button>
            </div>
          </form>
        )}

        {step === 2 && (
          <div className="card">
            <h2>Add a student</h2>
            <p className="muted" style={{ marginTop: -6, fontSize: 13 }}>
              Add your first child or student. You can add more later from the dashboard.
            </p>

            {students.length > 0 && (
              <ul className="checklist" style={{ marginBottom: 12 }}>
                {students.map((s) => (
                  <li key={s.id}>
                    <span className="check-dot done">&#10003;</span> {s.display_name}
                  </li>
                ))}
              </ul>
            )}

            <label htmlFor="student-name">Student name</label>
            <input
              id="student-name"
              value={newStudentName}
              onChange={(e) => setNewStudentName(e.target.value)}
              placeholder="Enter student name"
            />
            <label htmlFor="student-age">Age group</label>
            <select id="student-age" value={newStudentAge} onChange={(e) => setNewStudentAge(e.target.value)}>
              {AGE_RANGES.map((a) => (
                <option key={a.key} value={a.key}>
                  {a.label}
                </option>
              ))}
            </select>
            <label htmlFor="student-device-label">Device or profile label (optional)</label>
            <input
              id="student-device-label"
              value={newDeviceLabel}
              onChange={(e) => setNewDeviceLabel(e.target.value)}
              placeholder="e.g. Chromebook"
            />

            {step2Error && <p style={{ color: "#991b1b", fontSize: 13 }}>{step2Error}</p>}

            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button type="button" className="secondary" disabled={step2Busy || !newStudentName.trim()} onClick={handleAddStudent}>
                {step2Busy ? "Adding..." : "Add another student"}
              </button>
              <button type="button" disabled={students.length === 0} onClick={() => setStep(3)}>
                Continue
              </button>
              <button type="button" className="secondary" onClick={finishLater}>
                Save and finish later
              </button>
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="card">
            <h2>Choose websites</h2>
            <p className="muted" style={{ marginTop: -6, fontSize: 13 }}>
              Choose the websites you want to include in your first screen-time rule.
            </p>

            {selectedWebsites.length > 0 && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 8 }}>
                {selectedWebsites.map((w) => (
                  <span key={w.id} className="badge none" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                    {w.label}
                    <button
                      type="button"
                      aria-label={`Remove ${w.label}`}
                      onClick={() => toggleWebsite(w.id)}
                      style={{ background: "none", border: "none", cursor: "pointer", padding: 0, color: "inherit" }}
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            )}

            <label htmlFor="website-search">Search websites</label>
            <input
              id="website-search"
              value={websiteSearch}
              onChange={(e) => setWebsiteSearch(e.target.value)}
              placeholder="TikTok, YouTube Shorts, Instagram Reels..."
            />
            <div
              role="listbox"
              aria-label="Website search results"
              style={{ maxHeight: 180, overflowY: "auto", border: "1px solid var(--border)", borderRadius: 8, marginTop: 6, marginBottom: 12 }}
            >
              {filteredCatalog.slice(0, 12).map((w) => (
                <label
                  key={w.id}
                  style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 10px", borderBottom: "1px solid var(--border)", fontWeight: 400, cursor: "pointer" }}
                >
                  <input type="checkbox" checked={false} onChange={() => toggleWebsite(w.id)} />
                  {w.label} <span className="muted" style={{ fontSize: 12 }}>{w.domain}{w.url_pattern || ""}</span>
                </label>
              ))}
              {websiteCatalog.length === 0 && (
                <p className="muted" style={{ fontSize: 13, padding: "6px 10px" }}>
                  Loading website catalog...
                </p>
              )}
              {websiteCatalog.length > 0 && filteredCatalog.length === 0 && (
                <p className="muted" style={{ fontSize: 13, padding: "6px 10px" }}>
                  No matches. Add it as a custom website below.
                </p>
              )}
            </div>

            <p className="muted" style={{ fontSize: 12, marginBottom: 4 }}>Add custom website</p>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <input placeholder="Display name" value={customLabel} onChange={(e) => setCustomLabel(e.target.value)} style={{ flex: "1 1 120px", marginBottom: 0 }} />
              <input placeholder="Domain (e.g. example.com)" value={customDomain} onChange={(e) => setCustomDomain(e.target.value)} style={{ flex: "1 1 140px", marginBottom: 0 }} />
              <input placeholder="Path (optional)" value={customPath} onChange={(e) => setCustomPath(e.target.value)} style={{ flex: "1 1 100px", marginBottom: 0 }} />
              <button type="button" className="secondary" disabled={step3Busy || !customDomain.trim()} onClick={handleAddCustomWebsite}>
                {step3Busy ? "Adding..." : "Add website"}
              </button>
            </div>
            {step3Error && <p style={{ color: "#991b1b", fontSize: 13 }}>{step3Error}</p>}

            <div style={{ display: "flex", gap: 8, marginTop: 16, flexWrap: "wrap" }}>
              <button type="button" disabled={selectedWebsiteIds.length === 0} onClick={() => setStep(4)}>
                Continue
              </button>
              <button type="button" className="secondary" onClick={finishLater}>
                Save and finish later
              </button>
            </div>
          </div>
        )}

        {step === 4 && (
          <div className="card">
            <h2>Create your first rule</h2>

            {selectedWebsites.length > 0 && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 10 }}>
                {selectedWebsites.map((w) => (
                  <span key={w.id} className="badge none">
                    {w.label}
                  </span>
                ))}
              </div>
            )}
            {selectedWebsites.length === 0 && (
              <p className="muted" style={{ fontSize: 13 }}>
                No websites selected yet. <button type="button" className="link-button" onClick={() => setStep(3)}>Go back and choose some.</button>
              </p>
            )}

            <label htmlFor="rule-name">Rule name</label>
            <input id="rule-name" value={ruleName} onChange={(e) => setRuleName(e.target.value)} />

            {students.length > 1 && (
              <>
                <label htmlFor="rule-student">Student</label>
                <select id="rule-student" value={ruleStudentId} onChange={(e) => setRuleStudentId(e.target.value)}>
                  {students.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.display_name}
                    </option>
                  ))}
                </select>
              </>
            )}

            <label htmlFor="rule-limit">Daily time limit (minutes)</label>
            <input id="rule-limit" type="number" min={1} value={dailyLimit} onChange={(e) => setDailyLimit(e.target.value)} />
            <p className="muted" style={{ marginTop: -6, marginBottom: 10, fontSize: 12 }}>
              The daily limit applies to the combined active time across all selected websites. First warning at 80%,
              final warning at 100%, with a 5-minute grace period before access is restricted.
            </p>

            <label htmlFor="rule-days">Active days</label>
            <select id="rule-days" value={dayPreset} onChange={(e) => setDayPreset(e.target.value)}>
              {DAY_PRESETS.map((d) => (
                <option key={d.key} value={d.key}>
                  {d.label}
                </option>
              ))}
            </select>

            <label htmlFor="rule-reset">Reset time (family timezone)</label>
            <input id="rule-reset" type="time" value={resetTime} onChange={(e) => setResetTime(e.target.value)} />

            {step4Error && <p style={{ color: "#991b1b", fontSize: 13 }}>{step4Error}</p>}
            <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
              <button type="button" disabled={step4Busy || !ruleStudentId || selectedWebsiteIds.length === 0} onClick={handleCreateRule}>
                {step4Busy ? "Creating..." : "Create rule and continue"}
              </button>
              <button type="button" className="secondary" onClick={finishLater}>
                Save and finish later
              </button>
            </div>
          </div>
        )}

        {step === 5 && (
          <div className="card">
            <h2>Connect a student device</h2>
            <p className="muted" style={{ marginTop: -6, fontSize: 13 }}>
              The browser extension is required for active tracking and browser-based restrictions. FocusSentinel only
              measures active time on the websites you selected -- it doesn't read messages, keystrokes, or page content.
            </p>

            {students.length > 1 && (
              <>
                <label htmlFor="device-student">Student</label>
                <select id="device-student" value={deviceStudentId} onChange={(e) => setDeviceStudentId(e.target.value)}>
                  {students.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.display_name}
                    </option>
                  ))}
                </select>
              </>
            )}

            <label htmlFor="device-name">Device label (optional)</label>
            <input id="device-name" value={newDeviceLabel} onChange={(e) => setNewDeviceLabel(e.target.value)} placeholder="e.g. Chromebook" />

            {!deviceToken ? (
              <button type="button" disabled={step5Busy || !deviceStudentId} onClick={handleConnectDevice}>
                {step5Busy ? "Connecting..." : "Connect device"}
              </button>
            ) : (
              <div style={{ background: "var(--accent-soft)", borderRadius: 10, padding: 12, marginTop: 8 }}>
                <p style={{ fontSize: 13, margin: "0 0 8px" }}>
                  Install the FocusSentinel browser extension, then paste this token into its setup screen. It's shown
                  only once.
                </p>
                <input readOnly value={deviceToken.token} onFocus={(e) => e.currentTarget.select()} style={{ fontFamily: "monospace", fontSize: 13 }} />
                <a href="/about" style={{ fontSize: 13 }}>
                  Installation instructions and troubleshooting
                </a>
              </div>
            )}

            {step5Error && <p style={{ color: "#991b1b", fontSize: 13 }}>{step5Error}</p>}

            {deviceToken && (
              <div style={{ marginTop: 10 }}>
                <button type="button" className="secondary" onClick={handleTestConnection}>
                  Test connection
                </button>
                {connectionCheck && (
                  <p className="muted" style={{ fontSize: 13, marginTop: 6 }}>
                    {connectionCheck}
                  </p>
                )}
              </div>
            )}

            <div style={{ display: "flex", gap: 8, marginTop: 16, flexWrap: "wrap" }}>
              <button type="button" onClick={handleCompleteSetup}>
                Complete setup
              </button>
              <button type="button" className="secondary" disabled={step5Busy} onClick={handleSkipDevice}>
                Finish later without connecting a device
              </button>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
