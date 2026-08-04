"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, clearToken } from "../../lib/api";
import { Header } from "../../components/Header";

export default function AccountPage() {
  const router = useRouter();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [busy, setBusy] = useState(false);

  function signOut() {
    clearToken();
    router.push("/");
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccess(false);
    if (newPassword !== confirmPassword) {
      setError("New password and confirmation don't match.");
      return;
    }
    setBusy(true);
    try {
      await api.changePassword(currentPassword, newPassword);
      setSuccess(true);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (e: any) {
      setError(e.message || "Could not change your password.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Header
        right={
          <a onClick={signOut} style={{ cursor: "pointer" }}>
            Sign out
          </a>
        }
      />
      <div className="container" style={{ maxWidth: 420 }}>
        <h1>Account</h1>
        <div className="card">
          <h2>Change password</h2>
          <form onSubmit={handleSubmit}>
            <label htmlFor="current-password">Current password</label>
            <input id="current-password" type="password" required value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} />
            <label htmlFor="new-password">New password</label>
            <input id="new-password" type="password" required minLength={8} value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
            <label htmlFor="confirm-password">Confirm new password</label>
            <input id="confirm-password" type="password" required minLength={8} value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} />
            {error && <p style={{ color: "#991b1b", fontSize: 13 }}>{error}</p>}
            {success && <p style={{ color: "#166534", fontSize: 13 }}>Password updated.</p>}
            <button type="submit" disabled={busy}>
              {busy ? "Saving..." : "Update password"}
            </button>
          </form>
        </div>
      </div>
    </>
  );
}
