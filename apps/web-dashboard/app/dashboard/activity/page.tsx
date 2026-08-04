"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, clearToken } from "../../../lib/api";
import { useRequireAuth } from "../../../lib/useRequireAuth";
import { Header } from "../../../components/Header";

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

const DAY_FILTERS = [7, 14, 30];

export default function ActivityHistoryPage() {
  const router = useRouter();
  const authOk = useRequireAuth();
  const [students, setStudents] = useState<{ id: string; display_name: string }[]>([]);
  const [selectedStudent, setSelectedStudent] = useState<string | null>(null);
  const [days, setDays] = useState(7);
  const [history, setHistory] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function signOut() {
    clearToken();
    router.push("/");
  }

  useEffect(() => {
    api
      .myFamilies()
      .then(async (fams) => {
        if (fams.length === 0) return;
        const s = await api.listStudents(fams[0].id);
        setStudents(s);
        if (s.length > 0) setSelectedStudent(s[0].id);
      })
      .catch((e: any) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!selectedStudent) return;
    setLoading(true);
    api
      .usageHistory(selectedStudent, days)
      .then(setHistory)
      .catch((e: any) => setError(e.message))
      .finally(() => setLoading(false));
  }, [selectedStudent, days]);

  if (!authOk) return null;

  return (
    <>
      <Header
        active="dashboard"
        right={
          <button type="button" className="link-button" onClick={signOut}>
            Sign out
          </button>
        }
      />
      <div className="container">
        <h1>Activity history</h1>
        <p className="muted">
          <a href="/dashboard">Back to dashboard</a>
        </p>

        {error && <p style={{ color: "#991b1b" }}>{error}</p>}

        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", marginBottom: 16 }}>
          {students.length > 1 && (
            <select value={selectedStudent || ""} onChange={(e) => setSelectedStudent(e.target.value)} style={{ width: "auto", marginBottom: 0 }}>
              {students.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.display_name}
                </option>
              ))}
            </select>
          )}
          <div style={{ display: "flex", gap: 6 }}>
            {DAY_FILTERS.map((d) => (
              <button key={d} className={d === days ? "" : "secondary"} onClick={() => setDays(d)} style={{ padding: "6px 12px", fontSize: 13, marginLeft: 0 }}>
                {d} days
              </button>
            ))}
          </div>
        </div>

        {loading && <p className="muted">Loading...</p>}

        {history &&
          history.days.map((day: any) => {
            const totalMinutes = Math.round(day.total_seconds / 60);
            const categories = Object.entries(day.total_seconds_by_category || {}) as [string, number][];
            return (
              <div className="card" key={day.date}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                  <strong>{new Date(day.date + "T00:00:00").toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })}</strong>
                  <span className="muted" style={{ fontSize: 13 }}>{totalMinutes} min total</span>
                </div>
                {categories.length === 0 ? (
                  <p className="muted" style={{ fontSize: 13, marginTop: 6, marginBottom: 0 }}>
                    No tracked activity.
                  </p>
                ) : (
                  <div style={{ marginTop: 8 }}>
                    {categories
                      .sort((a, b) => b[1] - a[1])
                      .map(([key, seconds]) => (
                        <div className="row" key={key}>
                          <span>{categoryLabel(key)}</span>
                          <span className="muted">{Math.round(seconds / 60)} min</span>
                        </div>
                      ))}
                  </div>
                )}
              </div>
            );
          })}

        {history && history.days.every((d: any) => d.total_seconds === 0) && (
          <p className="muted">No tracked activity in the last {days} days.</p>
        )}
      </div>
    </>
  );
}
