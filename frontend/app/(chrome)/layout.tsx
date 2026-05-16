"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { API_BASE } from "@/lib/api";

export default function ChromeLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const onMonitors = pathname.startsWith("/monitor");
  const [online, setOnline] = useState<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE}/health`)
      .then((r) => !cancelled && setOnline(r.ok))
      .catch(() => !cancelled && setOnline(false));
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <Link href="/" className="brand" style={{ textDecoration: "none", color: "inherit" }}>
            <span className="brand-mark">M</span>
            <span className="brand-text">
              <span className="brand-name">MIRA</span>
              <span className="brand-sub">Market Intelligence Agent</span>
            </span>
          </Link>

          <div className="tabs">
            <Link href="/" className={"tab " + (!onMonitors ? "active" : "")}>
              Report
            </Link>
            <Link href="/monitor" className={"tab " + (onMonitors ? "active" : "")}>
              Monitors
            </Link>
          </div>

          <div className="status">
            <span className={"dot-live " + (online === false ? "dot-offline" : "")} />
            <span>{online === false ? "API OFFLINE" : "API ONLINE"}</span>
            <span className="pipe">·</span>
            <span>grok-4.3</span>
          </div>
        </div>
      </header>

      {children}

      <footer className="footer">
        <div>
          <div className="col-title">MIRA</div>
          <div>Market Intelligence &amp; Research Agent</div>
          <div>v1 · CS-001 Rev. B</div>
        </div>
        <div>
          <div className="col-title">Endpoints</div>
          <div>POST /analyze</div>
          <div>GET&nbsp; /status/{"{id}"}</div>
          <div>POST /monitor_start</div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div className="col-title">Stack</div>
          <div>FastAPI · LangGraph · Postgres</div>
          <div>OpenRouter · grok-4.3</div>
        </div>
      </footer>
    </>
  );
}
