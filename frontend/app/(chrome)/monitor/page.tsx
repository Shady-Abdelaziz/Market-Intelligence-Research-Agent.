"use client";

import { useEffect, useMemo, useState } from "react";
import {
  deleteMonitor,
  listMonitors,
  monitorHistory,
  postMonitorStart,
} from "@/lib/api";

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

interface HistoryEntry {
  job_id: string;
  created_at: string;
  triggers_fired?: string[];
  alert_tag?: string | null;
  report?: any;
}

type FilterKey = "all" | "alert" | "watching" | "quiet";

function statusOf(m: Monitor, history: HistoryEntry[] | undefined): FilterKey {
  if (history && history.some((h) => (h.triggers_fired || []).length > 0)) return "alert";
  if (m.baseline_price_mean == null) return "quiet";
  return "watching";
}

function fmtPct(v: number) {
  return (v >= 0 ? "+" : "") + v.toFixed(2) + "%";
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
      // Fetch history per monitor in parallel
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
      setErr(e instanceof Error ? e.message : "failed");
    } finally {
      setBusy(false);
    }
  }

  async function remove(t: string) {
    await deleteMonitor(t);
    await refresh();
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
  const trippedToday = monitors.filter((m) => {
    const h = history[m.ticker];
    if (!h || !h.length) return false;
    const newest = h[0];
    if (!newest?.created_at) return false;
    return (
      (newest.triggers_fired || []).length > 0 &&
      Date.now() - new Date(newest.created_at).getTime() < 24 * 3600 * 1000
    );
  }).length;
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
            const status = statusOf(m, h);
            const report = newest?.report || null;
            const price = report?.market_snapshot?.price as number | undefined;
            const pct = report?.market_snapshot?.daily_change_pct as number | undefined;
            const vol = report?.market_snapshot?.volume as number | undefined;
            const sigma =
              price != null && m.baseline_price_mean != null && m.baseline_price_std
                ? ((price - m.baseline_price_mean) / m.baseline_price_std).toFixed(2)
                : "—";
            const volX =
              vol != null && m.baseline_volume_avg ? (vol / m.baseline_volume_avg).toFixed(2) : "—";
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
                    <div className="val">{trigs.includes("articles") ? "≥5" : "—"}</div>
                  </div>
                  <div className={"trig " + (trigs.includes("price_2sigma") ? "fired" : "")}>
                    <div className="lbl">Price σ</div>
                    <div className="val">{sigma}σ</div>
                  </div>
                  <div className={"trig " + (trigs.includes("volume_2x") ? "fired" : "")}>
                    <div className="lbl">Volume</div>
                    <div className="val">{volX === "—" ? "—" : volX + "×"}</div>
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
              <option value="604800">Weekly</option>
            </select>
          </div>
          <div className="field">
            <label>Calendar</label>
            <select defaultValue="nyse">
              <option value="nyse">NYSE trading days</option>
              <option value="nasdaq">NASDAQ trading days</option>
              <option value="247">24/7</option>
            </select>
          </div>
          <button className="btn" disabled={busy || !form.ticker.trim()} onClick={add}>
            {busy ? "Adding…" : "Start watching"}
          </button>
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
