import Link from "next/link";
import type { ReactNode } from "react";

export function Header({
  active,
  right,
}: {
  active?: "about" | "dashboard" | "disclaimer";
  right?: ReactNode;
}) {
  return (
    <header className="site-header">
      <div className="container header-inner">
        <Link href="/" className="brand">
          <span className="brand-mark">FS</span>
          <span>FocusSentinel</span>
        </Link>
        <nav className="site-nav">
          <Link href="/about" className={active === "about" ? "active" : ""}>
            About
          </Link>
          <Link href="/disclaimer" className={active === "disclaimer" ? "active" : ""}>
            Disclaimer
          </Link>
          {right}
        </nav>
      </div>
    </header>
  );
}
