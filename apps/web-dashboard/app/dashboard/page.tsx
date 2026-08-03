"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, clearToken } from "../../lib/api";

type Student = { id: string; display_name: string; family_id: string };
type TodayUsage = {
  total_seconds_by_category: Record<string, number>;
  active_warnings: { level: number; rule_id: string }[];
  active_restrictions: { rule_id: string; reason: string; scheduled_reset_at: string }[];
};

export default function DashboardPage() {
  const router = useRouter();
  const [families, setFamilies] = useState<{ id: string; name: string }[]>([]);
  const [students, setStudents] = useState<Student[]>([]);
  const [selectedStudent, setSelectedStudent] = useState<string | null>(null);
  const [usage, setUsage] = useState<TodayUsage | null>(null);
  const [pendingRequests, setPendingRequests] = useState<any[]>([]);
  const [health, setHealth] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);

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
      const [u, reqs, h] = await Promise.all([
        api.usageToday(selectedStudent),
        api.listExtensionRequests(selectedStudent, "pending"),
        api.deviceHealth(selectedStudent),
      ]);
      setUsage(u);
      setPendingRequests(reqs);
      setHealth(h);
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
    <div className="container">
      <nav>
        <a className="active">Parent dashboard</a>
        <a onClick={signOut} style={{ marginLeft: "auto", cursor: "pointer" }}>
          Sign out
        </a>
      </nav>
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
  );
}
