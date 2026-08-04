"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { api, getRole, getToken, homeForRole, setRole } from "../lib/api";

export function Header({
  active,
  right,
}: {
  active?: "about" | "dashboard" | "disclaimer";
  right?: ReactNode;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  // Defaults to "/" (the login page) for logged-out visitors and during
  // server render; once mounted, a signed-in user's brand link goes back to
  // their own dashboard/student view instead of bouncing them to login.
  const [brandHref, setBrandHref] = useState("/");

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setMenuOpen(false);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (!getToken()) return;
    const role = getRole();
    if (role) {
      setBrandHref(homeForRole(role));
      return;
    }
    api
      .me()
      .then((u) => {
        setRole(u.role);
        setBrandHref(homeForRole(u.role));
      })
      .catch(() => {
        /* non-fatal -- brand link just falls back to "/" */
      });
  }, []);

  return (
    <header className="site-header">
      <div className="container header-inner">
        <Link href={brandHref} className="brand" onClick={() => setMenuOpen(false)}>
          <span className="brand-mark">FS</span>
          <span>FocusSentinel</span>
        </Link>
        <button
          type="button"
          className="nav-toggle"
          aria-label={menuOpen ? "Close menu" : "Open menu"}
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen((v) => !v)}
        >
          <span />
          <span />
          <span />
        </button>
        <nav className={`site-nav ${menuOpen ? "open" : ""}`}>
          <Link href="/about" className={active === "about" ? "active" : ""} onClick={() => setMenuOpen(false)}>
            About
          </Link>
          <Link href="/disclaimer" className={active === "disclaimer" ? "active" : ""} onClick={() => setMenuOpen(false)}>
            Disclaimer
          </Link>
          {right}
        </nav>
      </div>
    </header>
  );
}
