"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, clearToken } from "../../lib/api";
import { useRequireAuth } from "../../lib/useRequireAuth";
import { Header } from "../../components/Header";

export default function AccountPage() {
  const router = useRouter();
  const authOk = useRequireAuth();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [busy, setBusy] = useState(false);

  const [role, setRole] = useState<string | null>(null);
  const [confirmText, setConfirmText] = useState("");
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  useEffect(() => {
    api
      .me()
      .then((u) => setRole(u.role))
      .catch(() => {
        /* non-fatal -- delete-account messaging just falls back to generic wording */
      });
  }, []);

  function signOut() {
    clearToken();
    router.push("/");
  }

  async function handleDeleteAccount() {
    setDeleteError(null);
    setDeleteBusy(true);
    try {
      await api.deleteAccount();
      signOut();
    } catch (e: any) {
      setDeleteError(e.message || "Could not delete your account.");
    } finally {
      setDeleteBusy(false);
    }
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

  if (!authOk) return null;

  return (
    <>
      <Header
        right={
          <button type="button" className="link-button" onClick={signOut}>
            Sign out
          </button>
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

        <div className="card">
          <h2>Delete account</h2>
          {role === "parent" ? (
            <p className="muted" style={{ fontSize: 13 }}>
              You can delete your account once every student profile in your family has been removed from the
              dashboard (each one, individually, under "All students" → Delete). Deleting your account is permanent
              and can't be undone.
            </p>
          ) : (
            <p className="muted" style={{ fontSize: 13 }}>
              This deletes your sign-in only. Your student profile and its history stay in place — only a parent can
              remove that. You'll just no longer be able to sign in yourself.
            </p>
          )}
          <label htmlFor="confirm-delete">Type DELETE to confirm</label>
          <input id="confirm-delete" value={confirmText} onChange={(e) => setConfirmText(e.target.value)} />
          {deleteError && <p style={{ color: "#991b1b", fontSize: 13 }}>{deleteError}</p>}
          <button className="danger" disabled={confirmText !== "DELETE" || deleteBusy} onClick={handleDeleteAccount}>
            {deleteBusy ? "Deleting..." : "Delete my account"}
          </button>
        </div>
      </div>
    </>
  );
}
