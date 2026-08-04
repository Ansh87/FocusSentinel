import Link from "next/link";

export function Footer() {
  return (
    <footer className="site-footer">
      <div className="container site-footer-inner">
        <span className="muted">© {new Date().getFullYear()} FocusSentinel</span>
        <nav className="site-footer-nav">
          <Link href="/about">About</Link>
          <Link href="/disclaimer">Disclaimer</Link>
        </nav>
      </div>
    </footer>
  );
}
