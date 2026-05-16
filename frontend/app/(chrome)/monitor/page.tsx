"use client";

import { useEffect, useMemo, useState } from "react";
import {
  deleteMonitor,
  listMonitors,
  monitorHistory,
  postMonitorStart,
} from "@/lib/api";

// statusOf only flags "alert" for fires within this window so the row
// stops glowing red the day after a hit. The header "Tripped today"
// counter uses the same window — they now agree visually.
const MONITOR_ALERT_WINDOW_MS = 24 * 3600 * 1000;
const MONITOR_REFRESH_INTERVAL_MS = 60_000;

interface Monitor {
  id: string;
  ticker: string;
  cadence_seconds: number;
  peers?: string[];
  active: boolean;
  last_run_at?: string | null;
  baseline_price_mean?: number | null;
  baseline_price_std?: number | null;
  baseline_volume_avg?: number | null;
}

interface TriggerSnapshot {
  new_articles?: number;
  price_sigma?: number | null;
  volume_ratio?: number | null;
  captured_at?: string;
}

interface HistoryEntry {
  job_id: string;
  created_at: string;
  triggers_fired?: string[];
  alert_tag?: string | null;
  monitor_trigger_snapshot?: TriggerSnapshot | null;
  report?: any;
}

type FilterKey = "all" | "alert" | "watching" | "quiet";

function recentlyFired(h: HistoryEntry[] | undefined): boolean {
  if (!h?.length) return false;
  return h.some((row) => {
    if (!row.created_at) return false;
    if (!(row.triggers_fired || []).length) return false;
    return Date.now() - new Date(row.created_at).getTime() < MONITOR_ALERT_WINDOW_MS;
  });
}

function statusOf(m: Monitor, history: HistoryEntry[] | undefined): FilterKey {
  if (recentlyFired(history)) return "alert";
  if (m.baseline_price_mean == null) return "quiet";
  return "watching";
}

function fmtPct(v: number) {
  return (v >= 0 ? "+" : "") + v.toFixed(2) + "%";
}

function fmtSnapshotPrice(s: TriggerSnapshot | null | undefined): string {
  if (!s || s.price_sigma == null) return "—";
  return s.price_sigma.toFixed(2) + "σ";
}

function fmtSnapshotVol(s: TriggerSnapshot | null | undefined): string {
  if (!s || s.volume_ratio == null) return "—";
  return s.volume_ratio.toFixed(2) + "×";
}

function fmtSnapshotArticles(s: TriggerSnapshot | null | undefined): string {
  if (!s || s.new_articles == null) return "—";
  return `${s.new_articles} new`;
}

export default function MonitorsView() {
  const [monitors, setMonitors] = useState<Monitor[]>([]);
  const [history, setHistory] = useState<Record<string, HistoryEntry[]>>({});
  const [filter, setFilter] = useState<FilterKey>("all");
  const [form, setForm] = useState({ ticker: "", peers: "", cadence: "86400" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function refresh() {
    try {
      const data = (await listMonitors()) as Monitor[];
      setMonitors(data);
      const all = await Promise.all(
        data.map(async (m) => [m.ticker, await monitorHistory(m.ticker)] as const),
      );
      setHistory(Object.fromEntries(all) as Record<string, HistoryEntry[]>);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Failed to list monitors");
    }
  }

  useEffect(() => {
    refresh();
    // Background ticks land out-of-band; without auto-refresh the page
    // shows stale state until the user navigates away and back. Gate on
    // visibilityState so a backgrounded tab doesn't poll uselessly.
    const onInterval = () => {
      if (typeof document === "undefined" || document.visibilityState === "visible") {
        refresh();
      }
    };
    const handle = setInterval(onInterval, MONITOR_REFRESH_INTERVAL_MS);
    return () => clearInterval(handle);
  }, []);

  async function add() {
    setErr(null);
    if (!form.ticker.trim()) {
      setErr("Ticker required");
      return;
    }
    setBusy(true);
    try {
      await postMonitorStart(
        form.ticker.toUpperCase(),
        parseInt(form.cadence) || 86400,
        form.peers.split(",").map((s) => s.trim()).filter(Boolean),
      );
      setForm({ ticker: "", peers: "", cadence: form.cadence });
      await refresh();
    } catch (e: unknown) {
      const raw = e instanceof Error ? e.message : "failed";
      // BASELINE_COMPUTE_FAILED:<ticker>:<reason> from lib/api.ts — render
      // the human-readable cause rather than a wire-format string.
      if (raw.startsWith("BASELINE_COMPUTE_FAILED:")) {
        const [, ticker, reason] = raw.split(":", 3);
        setErr(`Couldn't compute baselines for ${ticker} — ${reason}. Ticker may be delisted or yfinance is rate-limited.`);
      } else {
        setErr(raw);
      }
    } finally {
      setBusy(false);
    }
  }

  async function remove(t: string) {
    if (typeof window !== "undefined" && !window.confirm(`Stop monitoring ${t}?`)) {
      return;
    }
    try {
      await deleteMonitor(t);
      await refresh();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "delete failed");
    }
  }

  const counts = useMemo(() => {
    const c: Record<FilterKey, number> = { all: monitors.length, alert: 0, watching: 0, quiet: 0 };
    for (const m of monitors) {
      const s = statusOf(m, history[m.ticker]);
      c[s]++;
    }
    return c;
  }, [monitors, history]);

  const list = monitors.filter((m) => filter === "all" || statusOf(m, history[m.ticker]) === filter);
  const trippedToday = monitors.filter((m) => recentlyFired(history[m.ticker])).length;
  const alerts30d = monitors.reduce((s, m) => {
    const h = history[m.ticker] || [];
    return (
      s +
      h.filter((r) => {
        if (!r.created_at) return false;
        return (
          (r.triggers_fired || []).length > 0 &&
          Date.now() - new Date(r.created_at).getTime() < 30 * 86400 * 1000
        );
      }).length
    );
  }, 0);

  return (
    <main className="container">
      <header className="mon-head">
        <div>
          <div className="eyebrow">Persistent monitoring · trading-day cadence</div>
          <h1>Standing watch.</h1>
          <p>
            MIRA ticks each ticker at the open, computes 30-day baselines, and fires a proactive
            analysis when articles, price, or volume break out.
          </p>
        </div>
        <div className="mon-stats">
          <div className="mon-stat">
            <div className="v">{counts.all}</div>
            <div className="k">Under watch</div>
          </div>
          <div className="mon-stat">
            <div className={"v " + (trippedToday > 0 ? "alert" : "")}>{trippedToday}</div>
            <div className="k">Tripped today</div>
          </div>
          <div className="mon-stat">
            <div className="v">{alerts30d}</div>
            <div className="k">Alerts · 30 d</div>
          </div>
        </div>
      </header>

      <div className="filter-row">
        {(["all", "alert", "watching", "quiet"] as FilterKey[]).map((f) => (
          <button
            key={f}
            className={"filter " + (filter === f ? "active" : "")}
            onClick={() => setFilter(f)}
          >
            {f[0].toUpperCase() + f.slice(1)} <span className="count">{counts[f]}</span>
          </button>
        ))}
      </div>

      {monitors.length === 0 ? (
        <div className="card" style={{ padding: 36, textAlign: "center", color: "var(--muted)" }}>
          <div className="eyebrow" style={{ marginBottom: 10 }}>no active monitors</div>
          <div>Add a ticker below to begin proactive monitoring.</div>
        </div>
      ) : (
        <div className="monitor-list">
          {list.map((m) => {
            const h = history[m.ticker] || [];
            const newest = h[0];
            const trigs = (newest?.triggers_fired || []) as string[];
            const snapshot = newest?.monitor_trigger_snapshot;
            const status = statusOf(m, h);
            const report = newest?.report || null;
            const price = report?.market_snapshot?.price as number | undefined;
            const pct = report?.market_snapshot?.daily_change_pct as number | undefined;
            const alertCount = h.filter((r) => (r.triggers_fired || []).length > 0).length;
            return (
              <div className="monitor-row" key={m.ticker}>
                <div className="mr-tick">
                  <div className="sym">{m.ticker}</div>
                  <div className="co">{report?.company_name || "—"}</div>
                </div>
                <div className="mr-status">
                  <span className={"mr-badge " + status}>
                    <span className="d" />
                    {status === "alert" ? "Alert today" : status === "watching" ? "Watching" : "Quiet"}
                  </span>
                  <div style={{ marginTop: 8 }}>
                    {price != null ? (
                      <>
                        <span className="price">${price.toFixed(2)}</span>
                        {pct != null && (
                          <span className={"pct " + (pct >= 0 ? "up" : "down")}>{fmtPct(pct)}</span>
                        )}
                      </>
                    ) : (
                      <span className="mono" style={{ color: "var(--muted)", fontSize: 12 }}>
                        awaiting first tick
                      </span>
                    )}
                  </div>
                </div>
                <div className="trigs">
                  <div className={"trig " + (trigs.includes("articles") ? "fired" : "")}>
                    <div className="lbl">Articles</div>
                    <div className="val">
                      {trigs.includes("articles") ? fmtSnapshotArticles(snapshot) : "—"}
                    </div>
                  </div>
                  <div className={"trig " + (trigs.includes("price_2sigma") ? "fired" : "")}>
                    <div className="lbl">Price σ</div>
                    <div className="val">
                      {trigs.includes("price_2sigma") ? fmtSnapshotPrice(snapshot) : "—"}
                    </div>
                  </div>
                  <div className={"trig " + (trigs.includes("volume_2x") ? "fired" : "")}>
                    <div className="lbl">Volume</div>
                    <div className="val">
                      {trigs.includes("volume_2x") ? fmtSnapshotVol(snapshot) : "—"}
                    </div>
                  </div>
                </div>
                <div className="mr-meta">
                  <div>
                    <span className="k">PEERS</span> &nbsp;{(m.peers || []).join(", ") || "—"}
                  </div>
                  <div>
                    <span className="k">CADENCE</span> &nbsp;
                    {(m.cadence_seconds / 3600).toFixed(0)}h · trading days
                  </div>
                  <div>
                    <span className="k">LAST RUN</span> &nbsp;
                    {m.last_run_at ? new Date(m.last_run_at).toLocaleString() : "—"}
                  </div>
                </div>
                <div className="mr-alerts">
                  <div className={"n " + (alertCount ? "has" : "zero")}>{alertCount}</div>
                  <div className="k">Alerts · history</div>
                  <div className="mr-actions">
                    {newest?.job_id && <a href={`/jobs/${newest.job_id}`}>view</a>}
                    <button className="danger" onClick={() => remove(m.ticker)}>
                      stop
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <section className="section">
        <header className="section-head">
          <span className="num">Trigger rules</span>
          <h2>What wakes MIRA up.</h2>
          <p>Any one of three conditions, evaluated on every tick. NYSE trading-day calendar gates execution.</p>
        </header>
        <div className="legend-grid">
          {[
            { name: "≥ 5 new articles", rule: "Articles seen since last tick ≥ 5", icon: "A" },
            { name: "Price > 2σ from baseline", rule: "|close − 30 d mean| > 2 × 30 d std", icon: "σ" },
            { name: "Volume > 2× baseline", rule: "Volume > 2 × 30 d average volume", icon: "V" },
          ].map((t) => (
            <div key={t.name}>
              <div className="icon">{t.icon}</div>
              <div className="name">{t.name}</div>
              <div className="rule">{t.rule}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="add">
        <div className="title">Add a new watch.</div>
        <div className="desc">POST /monitor_start · per-ticker cron, persisted across restarts.</div>
        <div className="row">
          <div className="field">
            <label>Ticker</label>
            <input
              value={form.ticker}
              onChange={(e) => setForm({ ...form, ticker: e.target.value.toUpperCase() })}
              placeholder="AAPL"
            />
          </div>
          <div className="field">
            <label>Peers (comma-separated)</label>
            <input
              value={form.peers}
              onChange={(e) => setForm({ ...form, peers: e.target.value })}
              placeholder="MSFT, GOOGL"
            />
          </div>
          <div className="field">
            <label>Cadence</label>
            <select
              value={form.cadence}
              onChange={(e) => setForm({ ...form, cadence: e.target.value })}
            >
              <option value="3600">1 hour</option>
              <option value="14400">4 hours</option>
              <option value="86400">24 hours · trading days</option>
            </select>
          </div>
          <button className="btn" disabled={busy || !form.ticker.trim()} onClick={add}>
            {busy ? "Adding…" : "Start watching"}
          </button>
        </div>
        <div className="mono" style={{ marginTop: 10, fontSize: 11, color: "var(--muted)" }}>
          Trading calendar: NYSE (server-side, configurable via{" "}
          <span className="mono">MONITOR_TRADING_CALENDAR</span>). Minimum cadence 1 hour.
        </div>
        {err && (
          <div className="mono" style={{ color: "var(--neg)", marginTop: 10, fontSize: 11 }}>
            {err}
          </div>
        )}
      </section>
    </main>
  );
}
