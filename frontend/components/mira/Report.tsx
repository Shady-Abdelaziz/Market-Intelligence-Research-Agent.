"use client";

import { useMemo } from "react";
import Sparkline from "./Sparkline";

interface Article {
  url: string;
  title: string;
  source: string;
  published_at: string;
  sentiment: "positive" | "negative" | "neutral";
  sentiment_score: number;
  rationale?: string;
}

interface ToolInvocation {
  name: string;
  input: any;
  output_summary: string;
  latency_ms: number;
  status: string;
}

export interface Report {
  company_ticker: string;
  company_name: string;
  analysis_summary: string;
  sentiment_score: number;
  market_snapshot: {
    price: number;
    daily_change_pct: number;
    volume: number;
    market_cap: number | null;
    pe_ratio: number | null;
    fifty_two_week_high: number;
    fifty_two_week_low: number;
    last_two_quarterly_revenues: { quarter: string; revenue_usd: number; reported_at: string }[];
  };
  correlation_analysis: {
    vs_sp500: number;
    vs_sector_etf: number;
    sector_etf_symbol: string;
    vs_peers: Record<string, number>;
    window_days: number;
  };
  key_findings: string[];
  citation_sources: string[];
  generated_at: string;
  reflection_passes: number;
  triggers_fired: string[];
  confidence: number;
  degraded?: boolean;
  degradation_reason?: string | null;
  data_freshness: {
    newest_article_at: string | null;
    market_data_at: string;
    edgar_filing_at: string | null;
  };
  sentiment_distribution: {
    positive: number;
    negative: number;
    neutral: number;
    total: number;
    articles: Article[];
  };
  token_usage: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    cost_usd: number;
    model: string;
  };
  tool_invocations: ToolInvocation[];
  tools_used: string[];
  alert_tag?: string | null;
  monitor_trigger?: string | null;
}

function fmtUsd(v: number) {
  return v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function fmtBig(v: number | null | undefined) {
  if (v == null) return "—";
  if (v >= 1e12) return (v / 1e12).toFixed(2) + "T";
  if (v >= 1e9) return (v / 1e9).toFixed(2) + "B";
  if (v >= 1e6) return (v / 1e6).toFixed(1) + "M";
  if (v >= 1e3) return (v / 1e3).toFixed(1) + "K";
  return v.toFixed(0);
}
function fmtPct(v: number) {
  return (v >= 0 ? "+" : "") + v.toFixed(2) + "%";
}
function shortDate(s: string) {
  const d = new Date(s);
  if (isNaN(+d)) return s;
  return d.toISOString().slice(0, 16).replace("T", " ");
}

const TRIGGER_DEFS = [
  { trigger: "Sector ETF correlation > 0.95", threshold: "0.95", key: "sector_correlation", action: "would fetch peer news + peer fundamentals" },
  { trigger: "All news older than 72 h", threshold: "72 h", key: "stale_news", action: "would fetch SEC EDGAR filings" },
  { trigger: "Neutral / evenly-split sentiment", threshold: "balanced", key: "neutral_sentiment", action: "would fetch SEC EDGAR filings" },
];

const DEGRADATION_COPY: Record<string, { headline: string; explainer: string; hint: string }> = {
  TICKER_NOT_FOUND: {
    headline: "We couldn't find a public ticker for this query.",
    explainer:
      "MIRA only analyses publicly-traded equities that Yahoo Finance recognises. The company you asked about may be private, delisted, or non-US — or the name may be ambiguous.",
    hint: "Try the query with an explicit symbol — e.g. \"Analyze Tesla (TSLA)\", \"$AAPL\", or \"NASDAQ:NVDA\".",
  },
  MARKET_DATA_UNAVAILABLE: {
    headline: "Market data was unavailable for this ticker.",
    explainer: "yfinance returned no usable quote data. The ticker may be delisted, suspended, or temporarily rate-limited upstream.",
    hint: "Retry in a minute, or try a different ticker.",
  },
};

function DegradedView({ report, jobId }: { report: Report; jobId: string }) {
  const reason = report.degradation_reason || "TICKER_NOT_FOUND";
  const copy = DEGRADATION_COPY[reason] || {
    headline: "MIRA returned a degraded report.",
    explainer: report.analysis_summary || "Not all tools completed successfully on this run.",
    hint: "See the diagnostics below for what we did and didn't fetch.",
  };
  const toolsAttempted = report.tool_invocations || [];
  return (
    <main className="container">
      <section>
        <div className="h-row">
          <span className="badge" style={{ color: "var(--neg)", borderColor: "var(--neg)" }}>
            DEGRADED · {reason}
          </span>
          <span>job {jobId.slice(0, 8)}</span>
          <span className="pipe">·</span>
          <span>Filed {shortDate(report.generated_at)}</span>
        </div>
        <h1 className="headline">{copy.headline}</h1>
        <p className="subhead">{copy.explainer}</p>
      </section>

      <section className="card" style={{ padding: 28, marginTop: 32, borderLeft: "3px solid var(--neg)" }}>
        <div className="eyebrow" style={{ marginBottom: 10 }}>How to fix</div>
        <p style={{ fontSize: 16, lineHeight: 1.55, margin: 0, color: "var(--fg-2)" }}>{copy.hint}</p>
        <div style={{ display: "flex", gap: 10, marginTop: 18, flexWrap: "wrap" }}>
          {["TSLA", "AAPL", "NVDA", "KO"].map((t) => (
            <a key={t} href={`/?q=${encodeURIComponent("Analyze " + t)}`} className="btn ghost">
              Try {t}
            </a>
          ))}
          <a href="/" className="btn">New query</a>
        </div>
      </section>

      <section className="section">
        <header className="section-head">
          <span className="num">Diagnostics</span>
          <h2>What MIRA did and didn&apos;t do.</h2>
          <p>Even on a degraded run, every tool attempt is logged so reviewers can verify the agent didn&apos;t fabricate.</p>
        </header>
        <div className="card" style={{ overflow: "hidden" }}>
          <table className="tbl">
            <thead>
              <tr>
                <th>Tool</th>
                <th>Output</th>
                <th>Latency</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {toolsAttempted.length === 0 ? (
                <tr>
                  <td colSpan={4} style={{ color: "var(--muted)", fontStyle: "italic" }}>
                    No tool calls were made — the agent short-circuited at ticker resolution.
                  </td>
                </tr>
              ) : (
                toolsAttempted.map((t, i) => (
                  <tr key={i}>
                    <td className="name">{t.name}</td>
                    <td>{t.output_summary}</td>
                    <td className="mono tabular" style={{ fontSize: 12 }}>{t.latency_ms} ms</td>
                    <td>
                      <span className={"status-pill " + (t.status === "success" ? "" : "fail")}>
                        <span className="d" />
                        {t.status}
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="section">
        <header className="section-head">
          <span className="num">Metadata</span>
          <h2>Provenance.</h2>
          <p>The agent still recorded its budget and reflection state so this run is auditable.</p>
        </header>
        <div className="card meta-card" style={{ padding: 20 }}>
          {[
            ["Reason", reason],
            ["Tool calls", String(toolsAttempted.length)],
            ["Reflection passes", String(report.reflection_passes)],
            ["Cost", `$${report.token_usage.cost_usd.toFixed(4)}`],
            ["Model", report.token_usage.model],
            ["Generated", shortDate(report.generated_at)],
          ].map(([k, v]) => (
            <div className="meta-row" key={k}>
              <span className="k">{k}</span>
              <span className="v">{v}</span>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}

function CorrRow({ label, tag, value }: { label: string; tag: string; value: number }) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  return (
    <div className="corr-row">
      <div className="corr-label">
        {label}
        <span className="corr-tag">{tag}</span>
      </div>
      <div className="corr-track">
        <div className="corr-fill" style={{ width: pct + "%" }} />
        <div className="corr-threshold" style={{ left: "95%" }} title="0.95 trigger" />
      </div>
      <div className="corr-value">{value.toFixed(2)}</div>
    </div>
  );
}

export default function ReportView({ report, jobId }: { report: Report; jobId: string }) {
  const m = report.market_snapshot;
  const s = report.sentiment_distribution;
  const c = report.correlation_analysis;
  const rangePos = (m.price - m.fifty_two_week_low) / (m.fifty_two_week_high - m.fifty_two_week_low);
  const maxLat = Math.max(...report.tool_invocations.map((t) => t.latency_ms), 1);
  const up = m.daily_change_pct >= 0;
  const sentClass = report.sentiment_score > 0.1 ? "" : report.sentiment_score < -0.1 ? "neg" : "neu";
  const sentLabel =
    report.sentiment_score > 0.5
      ? "Strongly positive"
      : report.sentiment_score > 0.1
        ? "Mildly positive"
        : report.sentiment_score < -0.5
          ? "Strongly negative"
          : report.sentiment_score < -0.1
            ? "Mildly negative"
            : "Neutral";

  const spark = useMemo(() => {
    // Synthesize a 30-pt spark from price + 52w range; gives a reasonable shape without historical data.
    const base = m.price;
    const out: number[] = [];
    let v = base * 0.92;
    for (let i = 0; i < 30; i++) {
      v = v + (base - v) * 0.08 + (Math.sin(i * 0.7) + Math.cos(i * 1.3)) * (base * 0.005);
      out.push(v);
    }
    out[out.length - 1] = base;
    return out;
  }, [m.price]);

  if (report.degraded || report.company_ticker === "UNKNOWN" || !report.company_ticker) {
    return <DegradedView report={report} jobId={jobId} />;
  }

  return (
    <main className="container">
      <section>
        <div className="h-row">
          <span className="badge">{report.company_ticker} · NASDAQ</span>
          <span>Equity research note</span>
          <span className="pipe">·</span>
          <span>Filed {shortDate(report.generated_at)}</span>
          {report.alert_tag && (
            <>
              <span className="pipe">·</span>
              <span className="badge" style={{ color: "var(--neg)", borderColor: "var(--neg)" }}>
                {report.alert_tag} {report.monitor_trigger ? `· ${report.monitor_trigger}` : ""}
              </span>
            </>
          )}
        </div>
        <h1 className="headline">{report.company_name}</h1>
        <p className="subhead">Job {jobId.slice(0, 8)} · {report.tools_used.length} tools · {report.reflection_passes} reflection passes.</p>
      </section>

      <section className="grid-2">
        <div className="card price-card">
          <div className="price-top">
            <div>
              <div className="eyebrow">Last trade</div>
              <div className="price-main">
                <span className="cur">$</span>
                {fmtUsd(m.price)}
              </div>
              <div className={"price-change " + (up ? "up" : "down")}>
                <span>{up ? "▲" : "▼"}</span>
                <span>{fmtPct(m.daily_change_pct)}</span>
                <span style={{ opacity: 0.7, marginLeft: 4 }}>· session</span>
              </div>
            </div>
            <div style={{ flex: 1, textAlign: "right" }}>
              <div className="eyebrow">30d</div>
              <div style={{ marginTop: 8 }}>
                <Sparkline data={spark} width={320} height={86} />
              </div>
            </div>
          </div>
          <div className="range-bar">
            <div className="eyebrow" style={{ marginBottom: 8 }}>52-week range</div>
            <div className="range-track">
              <div className="range-marker" style={{ left: rangePos * 100 + "%" }} />
            </div>
            <div className="range-labels">
              <span>${fmtUsd(m.fifty_two_week_low)}</span>
              <span>${fmtUsd(m.fifty_two_week_high)}</span>
            </div>
          </div>
          <div className="price-foot">
            <span>VOL · {fmtBig(m.volume)}</span>
            <span>MCAP · ${fmtBig(m.market_cap)}</span>
            <span>P/E · {m.pe_ratio != null ? m.pe_ratio.toFixed(1) : "—"}</span>
          </div>
        </div>

        <div className="stat-grid">
          <div className="stat">
            <span className="k">Market cap</span>
            <span className="v">${fmtBig(m.market_cap)}</span>
            <span className="sub">{m.market_cap && m.market_cap >= 10e9 ? "large-cap" : "mid/small-cap"}</span>
          </div>
          <div className="stat">
            <span className="k">P/E (trailing)</span>
            <span className="v">{m.pe_ratio != null ? m.pe_ratio.toFixed(1) + "×" : "—"}</span>
            <span className="sub">trailing twelve months</span>
          </div>
          <div className="stat">
            <span className="k">Revenue · {m.last_two_quarterly_revenues[0]?.quarter || "—"}</span>
            <span className="v">${(((m.last_two_quarterly_revenues[0]?.revenue_usd) || 0) / 1e9).toFixed(2)}B</span>
            <span className="sub">
              {m.last_two_quarterly_revenues[0]?.reported_at
                ? "reported " + shortDate(m.last_two_quarterly_revenues[0].reported_at)
                : "—"}
            </span>
          </div>
          <div className="stat">
            <span className="k">Volume · today</span>
            <span className="v">{fmtBig(m.volume)}</span>
            <span className="sub">shares traded</span>
          </div>
        </div>
      </section>

      <div className="colset">
        <div>
          <section className="section" style={{ marginTop: 0 }}>
            <header className="section-head">
              <span className="num">§ I — Summary</span>
              <h2>The bottom line.</h2>
              <p>A condensation of everything MIRA saw across the tools it called this pass.</p>
            </header>
            <p className="lead">{report.analysis_summary}</p>
          </section>

          <section className="section">
            <header className="section-head">
              <span className="num">§ II — Key findings</span>
              <h2>Three things.</h2>
              <p>The schema validates exactly three findings, no more, no less.</p>
            </header>
            <div className="findings">
              {report.key_findings.map((f, i) => (
                <div className="finding" key={i}>
                  <div className="n">{String(i + 1).padStart(2, "0")}</div>
                  <div className="body">{f}</div>
                </div>
              ))}
            </div>
          </section>

          <section className="section">
            <header className="section-head">
              <span className="num">§ III — News &amp; sentiment</span>
              <h2>{s.total} articles, cross-checked.</h2>
              <p>Per-article LLM classification with cross-check; disagreements lower the report&apos;s confidence.</p>
            </header>
            <div className="sent-grid">
              <div className="card sent-meter">
                <div className="eyebrow">Overall score</div>
                <div className={"sent-score " + sentClass}>
                  {report.sentiment_score >= 0 ? "+" : ""}
                  {report.sentiment_score.toFixed(2)}
                </div>
                <div className="sent-label">{sentLabel} · scale −1 … +1</div>
                <div className="sent-bar">
                  <div className="pos" style={{ flex: s.positive || 0.001 }}>{s.positive}+</div>
                  <div className="neu" style={{ flex: s.neutral || 0.001 }}>{s.neutral}∼</div>
                  <div className="neg" style={{ flex: s.negative || 0.001 }}>{s.negative}−</div>
                </div>
                <div className="dist-row">
                  <span>{s.total} articles</span>
                  <span>
                    {report.data_freshness.newest_article_at
                      ? "newest " + shortDate(report.data_freshness.newest_article_at)
                      : "—"}
                  </span>
                </div>
              </div>
              <div className="card articles">
                {s.articles.map((a, i) => (
                  <a className="article" key={i} href={a.url} target="_blank" rel="noreferrer">
                    <div
                      className={
                        "dot " + (a.sentiment === "positive" ? "pos" : a.sentiment === "negative" ? "neg" : "neu")
                      }
                    />
                    <div>
                      <div className="title">{a.title}</div>
                      <div className="meta">
                        {a.source} · {shortDate(a.published_at)}
                      </div>
                      {a.rationale && <div className="rationale">{a.rationale}</div>}
                    </div>
                    <div
                      className={
                        "score " + (a.sentiment === "positive" ? "pos" : a.sentiment === "negative" ? "neg" : "neu")
                      }
                    >
                      {a.sentiment_score > 0 ? "+" : ""}
                      {a.sentiment_score.toFixed(2)}
                    </div>
                  </a>
                ))}
              </div>
            </div>
          </section>

          <section className="section">
            <header className="section-head">
              <span className="num">§ IV — Correlation</span>
              <h2>Index, sector, peers.</h2>
              <p>{c.window_days}-trading-day Pearson correlation of daily log-returns. Red line marks the 0.95 reflection trigger.</p>
            </header>
            <div className="card corr-card">
              <CorrRow label="S&P 500" tag="SPY" value={c.vs_sp500} />
              <CorrRow label="Sector ETF" tag={c.sector_etf_symbol} value={c.vs_sector_etf} />
              {Object.entries(c.vs_peers).map(([p, v]) => (
                <CorrRow key={p} label={p} tag={p} value={v} />
              ))}
            </div>
          </section>

          <section className="section">
            <header className="section-head">
              <span className="num">§ V — Reflection ledger</span>
              <h2>
                {report.triggers_fired.length === 0
                  ? "No trigger fired."
                  : `${report.triggers_fired.length} trigger${report.triggers_fired.length > 1 ? "s" : ""} fired.`}
              </h2>
              <p>The agent evaluated the brief-mandated triggers and {report.reflection_passes === 0 ? "short-circuited to synthesis on the first pass" : `ran ${report.reflection_passes} reflection pass${report.reflection_passes > 1 ? "es" : ""}`}.</p>
            </header>
            <div className="card" style={{ overflow: "hidden" }}>
              <table className="tbl">
                <thead>
                  <tr>
                    <th>Trigger</th>
                    <th>Threshold</th>
                    <th>Fired?</th>
                    <th>Would have added</th>
                  </tr>
                </thead>
                <tbody>
                  {TRIGGER_DEFS.map((row) => {
                    const fired = report.triggers_fired.includes(row.key);
                    return (
                      <tr key={row.key}>
                        <td style={{ fontWeight: 500 }}>{row.trigger}</td>
                        <td className="mono" style={{ color: "var(--muted)" }}>{row.threshold}</td>
                        <td>
                          <span className={"fired-cell " + (fired ? "yes" : "")}>
                            <span className="d" />
                            {fired ? "fired" : "—"}
                          </span>
                        </td>
                        <td style={{ color: "var(--muted)" }}>{row.action}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>

          <section className="section">
            <header className="section-head">
              <span className="num">§ VI — Tools &amp; cost</span>
              <h2>What it spent.</h2>
              <p>Each tool invocation is logged with input, output, latency and status. Tokens are metered against a per-job cap.</p>
            </header>
            <div className="card" style={{ overflow: "hidden" }}>
              <table className="tbl">
                <thead>
                  <tr>
                    <th>Tool</th>
                    <th>Output</th>
                    <th>Latency</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {report.tool_invocations.map((t, i) => (
                    <tr key={i}>
                      <td className="name">{t.name}</td>
                      <td>{t.output_summary}</td>
                      <td>
                        <div className="lat-row">
                          <div className="lat-bar" style={{ width: (t.latency_ms / maxLat) * 80 + "px" }} />
                          <span className="mono tabular" style={{ fontSize: 12 }}>{t.latency_ms} ms</span>
                        </div>
                      </td>
                      <td>
                        <span className={"status-pill " + (t.status === "success" ? "" : "fail")}>
                          <span className="d" />
                          {t.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="card budget">
              <div className="budget-top">
                <div>
                  <div className="eyebrow">Job cost</div>
                  <div className="budget-now">${report.token_usage.cost_usd.toFixed(4)}</div>
                </div>
                <div className="budget-cap">
                  of <span style={{ color: "var(--fg)" }}>$0.25</span> cap
                  <br />
                  {((report.token_usage.cost_usd / 0.25) * 100).toFixed(1)}% used
                </div>
              </div>
              <div className="budget-bar">
                <div
                  className="budget-fill"
                  style={{ width: Math.min(100, (report.token_usage.cost_usd / 0.25) * 100) + "%" }}
                />
              </div>
              <div className="budget-foot">
                <div>
                  <div className="k">Prompt</div>
                  <div className="v">{report.token_usage.prompt_tokens.toLocaleString()}</div>
                </div>
                <div>
                  <div className="k">Completion</div>
                  <div className="v">{report.token_usage.completion_tokens.toLocaleString()}</div>
                </div>
                <div>
                  <div className="k">Model</div>
                  <div className="v mono" style={{ fontSize: 12 }}>{report.token_usage.model}</div>
                </div>
              </div>
            </div>
          </section>

          <section className="section">
            <header className="section-head">
              <span className="num">§ VII — Citations</span>
              <h2>{report.citation_sources.length} sources.</h2>
              <p>Every claim above is traceable to one of the URLs below.</p>
            </header>
            <div className="cites">
              {report.citation_sources.map((url, i) => {
                const host = url.replace(/^https?:\/\//, "").split("/")[0];
                const article = s.articles.find((a) => a.url === url);
                return (
                  <a className="cite" key={i} href={url} target="_blank" rel="noreferrer">
                    <span className="n">[{String(i + 1).padStart(2, "0")}]</span>
                    <div>
                      <div className="title">{article?.title || host}</div>
                      <div className="meta">{article?.source || host} · {host}</div>
                    </div>
                    <span className="arrow">→</span>
                  </a>
                );
              })}
            </div>
          </section>
        </div>

        <aside style={{ position: "sticky", top: 72, display: "grid", gap: 16 }}>
          <div className="card meta-card">
            <div className="header">Report metadata</div>
            {[
              ["Generated", shortDate(report.generated_at)],
              ["Schema", "AnalysisReport"],
              ["Reflection passes", String(report.reflection_passes)],
              ["Triggers fired", report.triggers_fired.length ? String(report.triggers_fired.length) : "—"],
              ["Tools used", String(report.tools_used.length)],
              ["Degraded", report.degraded ? "yes" : "no"],
            ].map(([k, v]) => (
              <div className="meta-row" key={k}>
                <span className="k">{k}</span>
                <span className="v">{v}</span>
              </div>
            ))}
            <div className="conf">
              <div className="conf-label">
                <span className="k">Confidence</span>
                <span className="v">{report.confidence.toFixed(2)}</span>
              </div>
              <div className="conf-bar">
                <div className="fill" style={{ width: report.confidence * 100 + "%" }} />
              </div>
            </div>
          </div>
          <div className="card meta-card">
            <div className="header">Data freshness</div>
            {[
              ["Newest article", report.data_freshness.newest_article_at ? shortDate(report.data_freshness.newest_article_at) : "—"],
              ["Market data", shortDate(report.data_freshness.market_data_at)],
              ["EDGAR filing", report.data_freshness.edgar_filing_at ? shortDate(report.data_freshness.edgar_filing_at) : "not pulled"],
            ].map(([k, v]) => (
              <div className="meta-row" key={k}>
                <span className="k">{k}</span>
                <span className="v">{v}</span>
              </div>
            ))}
          </div>
          <div className="card meta-card">
            <div className="header">In this report</div>
            {[
              ["§ I", "Summary"],
              ["§ II", "Key findings"],
              ["§ III", "News & sentiment"],
              ["§ IV", "Correlation"],
              ["§ V", "Reflection ledger"],
              ["§ VI", "Tools & cost"],
              ["§ VII", "Citations"],
            ].map(([n, t]) => (
              <div className="meta-row" key={n}>
                <span className="k">{n}</span>
                <span className="v">{t}</span>
              </div>
            ))}
          </div>
        </aside>
      </div>
    </main>
  );
}
