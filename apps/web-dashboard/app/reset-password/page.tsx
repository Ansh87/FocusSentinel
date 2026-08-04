"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "../../lib/api";
import { Header } from "../../components/Header";

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") || "";

  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (newPassword !== confirmPassword) {
      setError("Passwords don't match.");
      return;
    }
    setBusy(true);
    try {
      await api.resetPassword(token, newPassword);
      setSuccess(true);
    } catch (e: any) {
      setError(e.message || "This reset link is invalid or has expired.");
    } finally {
      setBusy(false);
    }
  }

  if (!token) {
    return (
      <div className="card">
        <p className="muted">This link is missing its reset token. Request a new one from the sign-in page.</p>
      </div>
    );
  }

  if (success) {
    return (
      <div className="card">
        <h2>Password updated</h2>
        <p className="muted">You can now sign in with your new password.</p>
        <button onClick={() => router.push("/")}>Go to sign in</button>
      </div>
    );
  }

  return (
    <div className="card">
      <h2>Choose a new password</h2>
      <form onSubmit={handleSubmit}>
        <label htmlFor="new-password">New password</label>
        <input id="new-password" type="password" required minLength={8} value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
        <label htmlFor="confirm-password">Confirm new password</label>
        <input id="confirm-password" type="password" required minLength={8} value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} />
        {error && <p style={{ color: "#991b1b", fontSize: 13 }}>{error}</p>}
        <button type="submit" disabled={busy}>
          {busy ? "Saving..." : "Reset password"}
        </button>
      </form>
    </div>
  );
}

export default function ResetPasswordPage() {
  return (
    <>
      <Header />
      <div className="container" style={{ maxWidth: 420 }}>
        <h1>Reset your password</h1>
        <Suspense fallback={<p className="muted">Loading...</p>}>
          <ResetPasswordForm />
        </Suspense>
      </div>
    </>
  );
}
