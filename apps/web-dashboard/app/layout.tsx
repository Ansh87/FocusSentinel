import "./globals.css";
import type { ReactNode } from "react";

export const metadata = {
  title: "FocusSentinel",
  description: "Healthy digital habits, without constant supervision.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
