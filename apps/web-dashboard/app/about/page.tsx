import { Header } from "../../components/Header";

export const metadata = {
  title: "About — FocusSentinel",
};

export default function AboutPage() {
  return (
    <>
    <Header active="about" />
    <div className="container">
      <h1>FocusSentinel</h1>
      <p className="muted">Healthy digital habits, without constant supervision.</p>

      <div className="card">
        <h2>What it does</h2>
        <p>
          FocusSentinel helps families set healthy screen-time boundaries for kids without
          constant manual supervision. Parents define daily time limits on specific categories
          of online activity — short-form video, social media, games, and more — and the system
          tracks usage automatically, delivers progressive warnings as a limit approaches, and
          applies a temporary restriction once it's crossed. If a student needs more time (for a
          school project, finishing something with friends, etc.), they can request an extension
          that a parent approves or denies remotely.
        </p>
      </div>

      <div className="card">
        <h2>How it works</h2>
        <ol className="step-list">
          <li>
            <span className="step-num">1</span>
            <span>
              <strong>Parent sets a limit.</strong> Pick a category — short-form video, social
              media, games — and a daily minute budget from the parent dashboard.
            </span>
          </li>
          <li>
            <span className="step-num">2</span>
            <span>
              <strong>Extension tracks real active time.</strong> Only foreground, focused-tab
              time on monitored sites counts. Switching tabs, going idle, or losing window focus
              pauses tracking automatically. No page content, messages, or keystrokes are ever
              collected.
            </span>
          </li>
          <li>
            <span className="step-num">3</span>
            <span>
              <strong>Usage syncs every ~30 seconds.</strong> The extension batches tracked time
              and sends it to the backend API, even working offline and catching up once
              reconnected.
            </span>
          </li>
          <li>
            <span className="step-num">4</span>
            <span>
              <strong>The rules engine evaluates it.</strong> As usage crosses 80% of the limit,
              then the limit itself, then a short grace period beyond it, the system raises a
              progress notice, a first warning, a second warning, and finally a restriction —
              each stage reflected live on the dashboard.
            </span>
          </li>
          <li>
            <span className="step-num">5</span>
            <span>
              <strong>Restriction is enforced in the browser.</strong> Once restricted, the
              extension blocks further access to that site directly, until the daily reset or a
              parent approves an extension request for more time.
            </span>
          </li>
        </ol>
      </div>

      <div className="card">
        <h2>Architecture</h2>
        <p>
          Built as a small set of independently deployable services: a FastAPI backend with
          PostgreSQL for data and JWT-based auth, a stateless rules engine as its own tested
          Python package, a Next.js parent dashboard, a Manifest V3 Chrome/Edge extension using
          <code> declarativeNetRequest</code> for real enforcement (not simulated), and a
          notification worker for warning/restriction alerts. Everything here is fully
          functional, not a mockup — the same code path a browser extension uses in production is
          exercised end-to-end by an automated test suite.
        </p>
      </div>

      <div className="card">
        <h2>Current scope &amp; honest limitations</h2>
        <p>
          This is an early, working version built to prove out the core tracking, warning, and
          restriction flow end-to-end, not yet a finished consumer product. It currently
          only sees activity inside a Chrome or Edge browser with the extension installed — there
          is no native Windows, macOS, Android, or iOS agent yet, so it cannot see or restrict
          usage inside native mobile apps (the TikTok app, Instagram app, etc.) on a phone, only
          browser-based access on a desktop where the extension is loaded. The extension also
          isn't published to an extension store yet, so it has to be installed manually rather
          than with a single click. Notification delivery is real code but running in "console
          mode" by default — actual email/SMS require adding provider credentials.
        </p>
      </div>

      <div className="card">
        <h2>What's next</h2>
        <p>
          Planned improvements include native mobile agents using each platform's screen-time
          APIs so restrictions apply to apps like TikTok and Instagram themselves and not just
          their websites, one-click browser extension installation via the Chrome Web Store, and
          real email/SMS notification delivery.
        </p>
      </div>
    </div>
    </>
  );
}
