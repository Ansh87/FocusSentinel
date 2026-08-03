"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, clearToken } from "../../lib/api";

// Simplification for this build: a full student-invite flow (parent invites
// a student email, student sets their own password, account gets linked to
// the students.user_id column) is a small follow-up, not implemented here.
// For now the student's own dashboard is addressed directly by student ID,
// which a parent shares with them during onboarding.

export default function StudentPage() {
  const router = useRouter();
  const [studentId, setStudentId] = useState("");
  const [usage, setUsage] = useState<any>(null);
  const [showForm, setShowForm] = useState(false);
  const [minutes, setMinutes] = useState(10);
  const [reason, setReason] = useState("friends");
  const [explanation, setExplanation] = useState("");
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    const saved = window.localStorage.getItem("focussentinel_student_id");
    if (saved) {
      setStudentId(saved);
      loadUsage(saved);
    }
  }, []);

  async function loadUsage(id: string) {
    try {
      const u = await api.usageToday(id);
      setUsage(u);
    } catch (e: any) {
      setStatus(e.message);
    }
  }

  function saveStudentId(e: React.FormEvent) {
    e.preventDefault();
    window.localStorage.setItem("focussentinel_student_id", studentId);
    loadUsage(studentId);
  }

  async function submitRequest(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api.requestExtension({
        student_id: studentId,
        requested_minutes: minutes,
        reason_code: reason,
        explanation,
      });
      setStatus("Request sent! You'll hear back from a parent or guardian soon.");
      setShowForm(false);
    } catch (e: any) {
      setStatus(e.message);
    }
  }

  function signOut() {
    clearToken();
    router.push("/");
  }

  return (
    <div className="container">
      <nav>
        <a className="active">My FocusSentinel</a>
        <a onClick={signOut} style={{ marginLeft: "auto", cursor: "pointer" }}>
          Sign out
        </a>
      </nav>

      {!usage && (
        <form onSubmit={saveStudentId} className="card">
          <label>Your student ID (ask a parent/guardian if you don't have it)</label>
          <input value={studentId} onChange={(e) => setStudentId(e.target.value)} required />
          <button type="submit">View my usage</button>
        </form>
      )}

      {usage && (
        <>
          <div className="card">
            <h2>What FocusSentinel measures</h2>
            <p className="muted">
              Only the time you actively spend, in the foreground, on activities your family enabled —
              never page content, messages, screenshots, or keystrokes.
            </p>
          </div>

          <div className="card">
            <h2>Today so far</h2>
            {Object.entries(usage.total_seconds_by_category || {}).map(([cat, seconds]: any) => (
              <div className="row" key={cat}>
                <span>{cat.replace(/_/g, " ")}</span>
                <span>{Math.round(seconds / 60)} min used</span>
              </div>
            ))}
            {usage.active_restrictions?.length > 0 && (
              <div className="row">
                <span className="badge restricted">Restricted</span>
                <span className="muted">
                  Available again at {new Date(usage.active_restrictions[0].scheduled_reset_at).toLocaleTimeString()}
                </span>
              </div>
            )}
          </div>

          <div className="card">
            <h2>Need more time?</h2>
            {!showForm && <button onClick={() => setShowForm(true)}>Request more time</button>}
            {showForm && (
              <form onSubmit={submitRequest}>
                <label>Minutes</label>
                <select value={minutes} onChange={(e) => setMinutes(Number(e.target.value))}>
                  <option value={5}>5</option>
                  <option value={10}>10</option>
                  <option value={15}>15</option>
                  <option value={30}>30</option>
                </select>
                <label>Reason</label>
                <select value={reason} onChange={(e) => setReason(e.target.value)}>
                  <option value="friends">Playing with friends</option>
                  <option value="special_event">Special event</option>
                  <option value="school_related">School-related use</option>
                  <option value="technical_issue">Technical issue</option>
                  <option value="other">Other</option>
                </select>
                <label>Anything else? (optional)</label>
                <textarea value={explanation} onChange={(e) => setExplanation(e.target.value)} rows={2} />
                <button type="submit">Send request</button>
              </form>
            )}
            {status && <p className="muted">{status}</p>}
          </div>
        </>
      )}
    </div>
  );
}
