import "./globals.css";
import type { ReactNode } from "react";
import { Footer } from "../components/Footer";

export const metadata = {
  title: "FocusSentinel",
  description: "Healthy digital habits, without constant supervision.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="page-shell">
          <div className="page-content">{children}</div>
          <Footer />
        </div>
      </body>
    </html>
  );
}
