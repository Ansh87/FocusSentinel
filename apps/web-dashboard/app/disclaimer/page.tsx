import { Header } from "../../components/Header";

export const metadata = {
  title: "Disclaimer — FocusSentinel",
};

export default function DisclaimerPage() {
  return (
    <>
      <Header active="disclaimer" />
      <div className="container">
        <h1>Disclaimer</h1>
        <p className="muted">Some context on who built this and what it is (and isn't).</p>

        <div className="card">
          <h2>About the developer</h2>
          <p>
            FocusSentinel was designed and built by <strong>Ansh Saini</strong>, a high school
            student, as an independent project. It was not built by a company, and it isn't a
            commercial product.
          </p>
        </div>

        <div className="card">
          <h2>Project status</h2>
          <p>
            This is a student-built demo / hackathon submission representing a first, working
            slice of a larger idea, not a finished, production-hardened application. It hasn't
            gone through a professional security audit, and it shouldn't be relied on as a sole
            safety or parental-control tool for a real child without further review. See the{" "}
            <a href="/about">About page</a> for an honest breakdown of what's actually implemented
            versus planned.
          </p>
        </div>

        <div className="card">
          <h2>No affiliation</h2>
          <p>
            FocusSentinel is an independent project and is not affiliated with, endorsed by, or
            sponsored by TikTok, Instagram, Meta, or any other platform referenced in this app.
            Those names are used only to describe the categories of activity the app can be
            configured to track.
          </p>
        </div>

        <div className="card">
          <h2>No warranty</h2>
          <p>
            This software is provided "as is," without warranty of any kind. The developer makes
            no guarantees about accuracy, uptime, or fitness for any particular purpose, and isn't
            liable for any outcome from using it.
          </p>
        </div>
      </div>
    </>
  );
}
