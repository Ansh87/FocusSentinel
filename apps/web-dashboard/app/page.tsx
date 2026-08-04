"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, setToken } from "../lib/api";
import { Header } from "../components/Header";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"signin" | "signup">("signin");

  const [email, setEmail] = useState("parent@focussentinel.demo");
  const [password, setPassword] = useState("demo-password-123");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  function switchMode(next: "signin" | "signup") {
    setMode(next);
    setError(null);
    setEmail(next === "signup" ? "" : "parent@focussentinel.demo");
    setPassword(next === "signup" ? "" : "demo-password-123");
    setDisplayName("");
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const result =
        mode === "signin"
          ? await api.login(email, password)
          : await api.register(email, password, displayName, "parent");
      setToken(result.access_token);
      router.push(result.role === "student" ? "/student" : "/dashboard");
    } catch (err: any) {
      setError(err.message || (mode === "signin" ? "Sign in failed" : "Could not create account"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <Header />
      <div className="container" style={{ maxWidth: 420, paddingTop: 48 }}>
        <h1>FocusSentinel</h1>
        <p className="muted">Healthy digital habits, without constant supervision.</p>
        <div className="card">
          <h2>{mode === "signin" ? "Sign in" : "Create your account"}</h2>
          <form onSubmit={handleSubmit}>
            {mode === "signup" && (
              <>
                <label>Your name</label>
                <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} type="text" required />
              </>
            )}
            <label>Email</label>
            <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" required />
            <label>Password</label>
            <input
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              type="password"
              required
              minLength={mode === "signup" ? 8 : undefined}
            />
            {mode === "signup" && (
              <p className="muted" style={{ marginTop: -6, marginBottom: 10, fontSize: 12 }}>
                At least 8 characters.
              </p>
            )}
            {error && <p style={{ color: "#991b1b" }}>{error}</p>}
            <button type="submit" disabled={loading}>
              {loading ? (mode === "signin" ? "Signing in..." : "Creating account...") : mode === "signin" ? "Sign in" : "Create account"}
            </button>
          </form>

          {mode === "signin" ? (
            <p className="muted" style={{ marginTop: 16, fontSize: 13 }}>
              New here?{" "}
              <a onClick={() => switchMode("signup")} style={{ cursor: "pointer", color: "var(--accent)" }}>
                Create an account
              </a>{" "}
              — no credit card, no real data needed, you can load a sample family right after.
            </p>
          ) : (
            <p className="muted" style={{ marginTop: 16, fontSize: 13 }}>
              Already have an account?{" "}
              <a onClick={() => switchMode("signin")} style={{ cursor: "pointer", color: "var(--accent)" }}>
                Sign in
              </a>
            </p>
          )}

          <p className="muted" style={{ marginTop: 12, fontSize: 13 }}>
            Demo parent login: parent@focussentinel.demo / demo-password-123
          </p>
        </div>
      </div>
    </>
  );
}
