"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, setToken } from "../lib/api";
import { Header } from "../components/Header";

const DEMO_EMAIL = "parent@focussentinel.demo";
const DEMO_PASSWORD = "demo-password-123";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"closed" | "signin" | "signup" | "forgot">("closed");

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [demoLoading, setDemoLoading] = useState(false);

  const [forgotEmail, setForgotEmail] = useState("");
  const [forgotBusy, setForgotBusy] = useState(false);
  const [forgotSent, setForgotSent] = useState(false);

  function switchMode(next: "signin" | "signup" | "forgot") {
    setMode(next);
    setError(null);
    setEmail("");
    setPassword("");
    setDisplayName("");
    setForgotSent(false);
  }

  async function handleForgotSubmit(e: React.FormEvent) {
    e.preventDefault();
    setForgotBusy(true);
    try {
      await api.requestPasswordReset(forgotEmail);
      setForgotSent(true);
    } catch {
      // Deliberately shown the same way as success — the endpoint itself
      // never reveals whether the email exists, and neither should this.
      setForgotSent(true);
    } finally {
      setForgotBusy(false);
    }
  }

  async function afterAuth(result: { access_token: string; role: string }) {
    setToken(result.access_token);
    router.push(result.role === "student" ? "/student" : "/dashboard");
  }

  async function handleTryDemo() {
    setDemoLoading(true);
    setError(null);
    try {
      const result = await api.login(DEMO_EMAIL, DEMO_PASSWORD);
      await afterAuth(result);
    } catch (err: any) {
      setError(err.message || "Could not open the interactive demo right now.");
    } finally {
      setDemoLoading(false);
    }
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
      await afterAuth(result);
    } catch (err: any) {
      setError(err.message || (mode === "signin" ? "Sign in failed" : "Could not create account"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <Header />
      <div className="container" style={{ maxWidth: 460, paddingTop: 56 }}>
        <h1>Building Healthier Digital Habits for Young Minds</h1>
        <p className="muted">
          Set healthy limits, track active use, and support balanced technology habits.
        </p>

        <div className="card">
          <button
            type="button"
            style={{ width: "100%", padding: "12px 14px", fontSize: 15 }}
            onClick={handleTryDemo}
            disabled={demoLoading}
          >
            {demoLoading ? "Opening demo..." : "Try the Interactive Demo"}
          </button>
          <p className="muted" style={{ fontSize: 12, textAlign: "center", margin: "8px 0 0" }}>
            Signs you into a fully populated sample family — no account needed.
          </p>

          <div style={{ display: "flex", alignItems: "center", gap: 10, margin: "18px 0" }}>
            <div style={{ flex: 1, height: 1, background: "var(--border)" }} />
            <span className="muted" style={{ fontSize: 12 }}>or</span>
            <div style={{ flex: 1, height: 1, background: "var(--border)" }} />
          </div>

          {mode === "closed" ? (
            <div style={{ display: "flex", gap: 8 }}>
              <button type="button" className="secondary" style={{ flex: 1 }} onClick={() => switchMode("signin")}>
                Sign in
              </button>
              <button type="button" className="secondary" style={{ flex: 1 }} onClick={() => switchMode("signup")}>
                Create an account
              </button>
            </div>
          ) : mode === "forgot" ? (
            <>
              <h2>Reset your password</h2>
              {forgotSent ? (
                <p className="muted" style={{ fontSize: 13 }}>
                  If that email has an account, we've queued a reset link to it. It'll expire in 30 minutes.
                </p>
              ) : (
                <form onSubmit={handleForgotSubmit}>
                  <label htmlFor="forgot-email">Email</label>
                  <input id="forgot-email" value={forgotEmail} onChange={(e) => setForgotEmail(e.target.value)} type="email" required />
                  <button type="submit" disabled={forgotBusy}>
                    {forgotBusy ? "Sending..." : "Send reset link"}
                  </button>
                </form>
              )}
              <button type="button" className="secondary" style={{ marginTop: 8 }} onClick={() => switchMode("signin")}>
                Back to sign in
              </button>
            </>
          ) : (
            <>
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
                <button type="button" className="secondary" onClick={() => setMode("closed")}>
                  Cancel
                </button>
              </form>

              <p className="muted" style={{ marginTop: 16, fontSize: 13 }}>
                {mode === "signin" ? (
                  <>
                    New here?{" "}
                    <a onClick={() => switchMode("signup")} style={{ cursor: "pointer", color: "var(--accent)" }}>
                      Create an account
                    </a>
                    {" · "}
                    <a onClick={() => switchMode("forgot")} style={{ cursor: "pointer", color: "var(--accent)" }}>
                      Forgot password?
                    </a>
                  </>
                ) : (
                  <>
                    Already have an account?{" "}
                    <a onClick={() => switchMode("signin")} style={{ cursor: "pointer", color: "var(--accent)" }}>
                      Sign in
                    </a>
                  </>
                )}
              </p>
            </>
          )}

          {error && mode === "closed" && <p style={{ color: "#991b1b", marginTop: 12 }}>{error}</p>}
        </div>
      </div>
    </>
  );
}
