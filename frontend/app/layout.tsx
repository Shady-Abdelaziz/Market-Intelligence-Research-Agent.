import "./globals.css";
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "M.I.R.A. — Market Intelligence & Research Agent",
  description: "Autonomous AI equity research agent",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen font-sans">
        <header className="border-b">
          <div className="mx-auto max-w-6xl flex items-center justify-between px-6 py-4">
            <Link href="/" className="flex items-center gap-2">
              <span className="text-2xl font-bold text-accent">M.I.R.A.</span>
              <span className="text-sm text-gray-500">· Market Intelligence Agent</span>
            </Link>
            <nav className="flex gap-6 text-sm">
              <Link href="/" className="hover:text-accent">Submit</Link>
              <Link href="/monitor" className="hover:text-accent">Monitors</Link>
              <a
                href={(process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000") + "/docs"}
                target="_blank"
                rel="noreferrer"
                className="hover:text-accent"
              >
                API docs
              </a>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
