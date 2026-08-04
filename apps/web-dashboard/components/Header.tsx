"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";

export function Header({
  active,
  right,
}: {
  active?: "about" | "dashboard" | "disclaimer";
  right?: ReactNode;
}) {
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setMenuOpen(false);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  return (
    <header className="site-header">
      <div className="container header-inner">
        <Link href="/" className="brand" onClick={() => setMenuOpen(false)}>
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
