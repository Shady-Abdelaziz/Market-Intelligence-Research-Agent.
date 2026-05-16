"use client";

import { createContext, useContext, useEffect, useRef, useState } from "react";
import {
  Btn,
  CiteChip,
  CorrBar,
  Eyebrow,
  Fade,
  KIND_COLORS,
  S,
  SentimentBar,
  Skel,
  Spark,
  SpectrumGlobals,
  Stat,
  Tag,
} from "./primitives";
import type { EventKind } from "./primitives";
import {
  TIMELINE_INITIAL,
  useAgentStream,
  useRealAgentStream,
} from "./stream";
import type {
  Citation,
  CurrentTool,
  Finding,
  StreamControlsValue,
  StreamState,
  TimelineEvent,
} from "./stream";

type ColorName = "coral" | "amber" | "azure" | "mint" | "violet" | "rose";

const COLOR_MAP: Record<ColorName, string> = {
  coral: S.coral,
  amber: S.amber,
  azure: S.azure,
  mint: S.mint,
  violet: S.violet,
  rose: S.rose,
};

const StreamCtx = createContext<{
  state: StreamState;
  controls: StreamControlsValue;
}>({
  state: TIMELINE_INITIAL,
  controls: {
    replay: () => {},
    togglePlay: () => {},
    playing: false,
    elapsed: 0,
    done: false,
  },
});

const useStream = () => useContext(StreamCtx);

function currentCost(state: StreamState) {
  const toolCalls =
    state.events.filter((e) => e.kind === "tool").length + (state.currentTool ? 1 : 0);
  return Math.min(0.018, toolCalls * 0.003);
}

function toolCallCount(state: StreamState) {
  return state.events.filter((e) => e.kind === "tool").length + (state.currentTool ? 1 : 0);
}

export default function SpectrumLive({ jobId }: { jobId?: string } = {}) {
  // When a jobId is provided we poll the backend for the persisted report.
  // Without one, fall back to the scripted Coca-Cola design preview.
  const real = useRealAgentStream(jobId ?? null);
  const demo = useAgentStream();
  const { state, controls } = jobId ? real : demo;

  // For real jobs: while the backend is still working, render a clean
  // "processing" screen instead of a half-populated dashboard.
  if (jobId && !state.done) {
    return <ProcessingScreen jobId={jobId} elapsed={controls.elapsed} query={state.query} />;
  }

  return (
    <StreamCtx.Provider value={{ state, controls }}>
      <SpectrumGlobals />
      <div
        className="sp sp-page"
        style={{
          minHeight: "100vh",
          background: S.bg,
          position: "relative",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            position: "absolute",
            top: -300,
            right: -200,
            width: 800,
            height: 800,
            background: `radial-gradient(circle, ${S.coralSoft} 0%, transparent 65%)`,
            pointerEvents: "none",
            zIndex: 0,
            opacity: 0.8,
          }}
        />
        <div
          style={{
            position: "absolute",
            bottom: -400,
            left: -200,
            width: 700,
            height: 700,
            background: `radial-gradient(circle, ${S.violetSoft} 0%, transparent 65%)`,
            pointerEvents: "none",
            zIndex: 0,
            opacity: 0.6,
          }}
        />

        <div style={{ position: "relative", zIndex: 1 }}>
          <SpectrumTopBar />
          <SpectrumHero />
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1.45fr 1fr",
              gap: 24,
              padding: "0 40px 40px",
              alignItems: "flex-start",
            }}
          >
            <SpectrumReport />
            <SpectrumAgent />
          </div>
          <SpectrumFooter />
        </div>
      </div>
    </StreamCtx.Provider>
  );
}

function ExportMenu({
  onJson,
  onPdf,
}: {
  onJson: () => void;
  onPdf: () => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);
  return (
    <div ref={ref} style={{ position: "relative" }}>
      <Btn
        ghost
        small
        onClick={() => setOpen((v) => !v)}
        iconRight={<span style={{ fontSize: 9 }}>▾</span>}
      >
        Export
      </Btn>
      {open && (
        <div
          role="menu"
          style={{
            position: "absolute",
            top: "calc(100% + 6px)",
            right: 0,
            minWidth: 180,
            padding: 6,
            background: S.surface,
            border: `1px solid ${S.border}`,
            borderRadius: 10,
            boxShadow: "0 10px 32px rgba(0,0,0,0.10)",
            zIndex: 60,
            display: "flex",
            flexDirection: "column",
            gap: 2,
          }}
        >
          {[
            { label: "Download JSON", sub: "raw report payload", run: onJson },
            { label: "Download PDF", sub: "print-formatted dossier", run: onPdf },
          ].map((it) => (
            <button
              key={it.label}
              role="menuitem"
              onClick={() => {
                setOpen(false);
                it.run();
              }}
              style={{
                appearance: "none",
                background: "transparent",
                border: "none",
                textAlign: "left",
                cursor: "pointer",
                padding: "10px 12px",
                borderRadius: 6,
                display: "flex",
                flexDirection: "column",
                gap: 2,
                fontFamily: S.fSans,
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = S.surfaceHi)}
              onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
            >
              <span style={{ fontSize: 13, color: S.text, fontWeight: 500 }}>
                {it.label}
              </span>
              <span className="sp-mono" style={{ fontSize: 10, color: S.text3 }}>
                {it.sub}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function SpectrumTopBar() {
  const { state, controls } = useStream();
  const status = state.done
    ? "filed"
    : state.currentTool
      ? "streaming"
      : state.events.length === 0
        ? "queued"
        : "thinking";
  const exportJson = () => {
    if (!state.report) return;
    const blob = new Blob([JSON.stringify(state.report, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `mira-${state.ticker || "report"}-${Date.now()}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };
  const exportPdf = () => window.print();
  const share = async () => {
    const url = window.location.href;
    try {
      await navigator.clipboard.writeText(url);
      alert("Dossier URL copied to clipboard");
    } catch {
      window.prompt("Copy the dossier URL:", url);
    }
  };
  return (
    <header
      style={{
        display: "flex",
        alignItems: "center",
        gap: 24,
        padding: "16px 40px",
        borderBottom: `1px solid ${S.border}`,
        backdropFilter: "blur(12px)",
        background: "rgba(247,245,240,0.78)",
        position: "sticky",
        top: 0,
        zIndex: 50,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div
          style={{
            width: 32,
            height: 32,
            borderRadius: 9,
            background: `linear-gradient(135deg, ${S.coral} 0%, ${S.violet} 100%)`,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "#fff",
            fontWeight: 700,
            fontSize: 14,
          }}
        >
          ✦
        </div>
        <div>
          <div style={{ fontSize: 14, fontWeight: 600, letterSpacing: -0.2 }}>M.I.R.A.</div>
          <div
            className="sp-mono"
            style={{ fontSize: 9, color: S.text3, letterSpacing: 0.6 }}
          >
            v1.0 · grok-4.3
          </div>
        </div>
      </div>

      <div style={{ width: 1, height: 24, background: S.border }} />

      <nav style={{ display: "flex", gap: 4 }}>
        {[
          { name: "Analyze", active: true },
          { name: "Monitor" },
          { name: "Archive" },
          { name: "Eval" },
        ].map((n) => (
          <span
            key={n.name}
            style={{
              padding: "8px 14px",
              fontSize: 13,
              fontWeight: 500,
              color: n.active ? S.text : S.text3,
              background: n.active ? S.surfaceHi : "transparent",
              borderRadius: 8,
              cursor: "pointer",
            }}
          >
            {n.name}
          </span>
        ))}
      </nav>

      <div style={{ flex: 1 }} />

      <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
        <Tag color={state.done ? S.mint : S.coral} dot>
          {!state.done && (
            <span
              className="sp-pulse"
              style={{
                display: "inline-block",
                width: 6,
                height: 6,
                borderRadius: "50%",
                background: S.coral,
                marginRight: -2,
              }}
            />
          )}
          {status}
        </Tag>
        <div
          className="sp-mono"
          style={{
            fontSize: 11,
            color: S.text2,
            padding: "5px 10px",
            background: S.surface,
            borderRadius: 8,
            border: `1px solid ${S.border}`,
          }}
        >
          <span style={{ color: S.text }}>
            ${(() => {
              const tu = state.report?.token_usage as Record<string, number> | undefined;
              return typeof tu?.cost_usd === "number"
                ? (tu.cost_usd as number).toFixed(4)
                : currentCost(state).toFixed(4);
            })()}
          </span>{" "}
          <span style={{ color: S.text3 }}>/ $0.05</span>
        </div>
        <span style={{ width: 1, height: 20, background: S.border, margin: "0 4px" }} />
        {state.done && (
          <div className="sp-no-print" style={{ display: "flex", gap: 8 }}>
            <Btn ghost small onClick={controls.replay}>
              ↻ Replay
            </Btn>
            <ExportMenu onJson={exportJson} onPdf={exportPdf} />
            <Btn primary small iconRight={<span>→</span>} onClick={share}>
              Share
            </Btn>
          </div>
        )}
        <span style={{ width: 1, height: 20, background: S.border, margin: "0 4px" }} />
        <div
          style={{
            width: 32,
            height: 32,
            borderRadius: 8,
            background: `linear-gradient(135deg, ${S.azure} 0%, ${S.mint} 100%)`,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 11,
            fontWeight: 700,
            color: "#fff",
          }}
        >
          AE
        </div>
      </div>
    </header>
  );
}

function SpectrumHero() {
  const { state } = useStream();
  const hasMarket = !!state.market;
  const hasSent = !!state.sentiment;
  const reflectN = (state.reflectionFired ? 1 : 0) + (state.replanned ? 1 : 0);
  const tickerPill = state.ticker
    ? `${state.exchange || "NYSE"} : ${state.ticker}`
    : "TICKER : PENDING";
  // Split the company name into a bold head ("Tesla") + a muted tail
  // ("Inc.") if the name has a trailing entity suffix; otherwise show the
  // whole thing in bold.
  const name = state.companyName || "Resolving…";
  const splitAt = name.search(/\b(Inc|Corp|Corporation|Company|Ltd|Plc|Group|Holdings)\.?$/i);
  const head = splitAt > 0 ? name.slice(0, splitAt).trim() : name;
  const tail = splitAt > 0 ? name.slice(splitAt) : null;
  return (
    <section style={{ padding: "48px 40px 40px" }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          marginBottom: 18,
          flexWrap: "wrap",
        }}
      >
        <a href="/" style={{ color: S.text3, fontSize: 13, textDecoration: "none" }}>
          ← Archive
        </a>
        <span style={{ color: S.text4 }}>·</span>
        <Eyebrow>{state.caseId ? `Case ${state.caseId}` : "Case pending"}</Eyebrow>
        {state.filedAt && (
          <>
            <span style={{ color: S.text4 }}>·</span>
            <Eyebrow>{state.filedAt}</Eyebrow>
          </>
        )}
        {state.alertTag && (
          <>
            <span style={{ color: S.text4 }}>·</span>
            <Fade in>
              <Tag color={S.coral} solid>
                Proactive alert
              </Tag>
            </Fade>
          </>
        )}
        {reflectN > 0 && (
          <>
            <span style={{ color: S.text4 }}>·</span>
            <Fade in>
              <Tag color={S.amber}>
                {reflectN} reflection{reflectN > 1 ? "s" : ""} fired
              </Tag>
            </Fade>
          </>
        )}
        {state.failed && (
          <>
            <span style={{ color: S.text4 }}>·</span>
            <Tag color={S.rose} solid>
              {state.failedReason || "failed"}
            </Tag>
          </>
        )}
      </div>

      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: 16,
          marginBottom: 14,
          flexWrap: "wrap",
        }}
      >
        <span
          className="sp-mono"
          style={{
            fontSize: 14,
            fontWeight: 600,
            color: S.coral,
            padding: "3px 9px",
            background: S.coralSoft,
            border: `1px solid ${S.coralLine}`,
            borderRadius: 4,
            letterSpacing: 1,
          }}
        >
          {tickerPill}
        </span>
        {state.sector && (
          <span style={{ color: S.text3, fontSize: 14 }}>{state.sector}</span>
        )}
        {state.marketCap && (
          <>
            <span style={{ color: S.text4 }}>·</span>
            <span style={{ color: S.text3, fontSize: 14 }}>{state.marketCap}</span>
          </>
        )}
      </div>

      <h1
        className="sp-h1"
        style={{
          fontSize: 88,
          fontWeight: 600,
          letterSpacing: "-0.035em",
          lineHeight: 1,
          whiteSpace: "nowrap",
        }}
      >
        {head}
        {tail && (
          <span style={{ color: S.text3, marginLeft: 18, fontWeight: 400 }}>{tail}</span>
        )}
      </h1>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1.4fr 1fr",
          gap: 40,
          alignItems: "end",
          marginTop: 36,
        }}
      >
        <div
          style={{
            padding: "16px 20px",
            background: S.surface,
            border: `1px solid ${S.border}`,
            borderLeft: `3px solid ${S.coral}`,
            borderRadius: 8,
          }}
        >
          <Eyebrow style={{ marginBottom: 6 }}>Operator&apos;s brief</Eyebrow>
          <div
            style={{
              fontSize: 17,
              color: S.text,
              fontWeight: 500,
              lineHeight: 1.4,
              letterSpacing: -0.2,
            }}
          >
            {state.query || "Awaiting query…"}
          </div>
        </div>

        <div
          style={{
            display: "flex",
            gap: 28,
            justifyContent: "flex-end",
            paddingBottom: 4,
          }}
        >
          {hasMarket && state.market ? (
            <Fade in>
              <Stat
                label="Last"
                value={state.market.price}
                delta={state.market.delta}
                size={30}
                align="right"
              />
            </Fade>
          ) : (
            <SkelStat label="Last" />
          )}
          <span style={{ width: 1, alignSelf: "stretch", background: S.border }} />
          {hasSent && state.sentiment ? (
            <Fade in>
              <Stat
                label="Sentiment"
                value={state.sentiment.score.toFixed(2)}
                sub={`conf ${state.sentiment.conf.toFixed(2)}`}
                size={30}
                align="right"
                deltaColor={S.text3}
              />
            </Fade>
          ) : (
            <SkelStat label="Sentiment" />
          )}
          <span style={{ width: 1, alignSelf: "stretch", background: S.border }} />
          <Stat
            label="Tools used"
            value={`${toolCallCount(state)} / 10`}
            sub={reflectN ? `${reflectN} reflection${reflectN > 1 ? "s" : ""}` : "—"}
            size={30}
            align="right"
            deltaColor={S.text3}
          />
        </div>
      </div>
    </section>
  );
}

function SkelStat({ label }: { label: string }) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 6,
        alignItems: "flex-end",
      }}
    >
      <Eyebrow>{label}</Eyebrow>
      <Skel w={110} h={28} />
      <Skel w={60} h={10} />
    </div>
  );
}

function SpectrumReport() {
  const { state } = useStream();
  const printDate = new Date().toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
  return (
    <main style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div className="sp-print-header" aria-hidden>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <div style={{ fontSize: 20, fontWeight: 700, letterSpacing: -0.4 }}>
            M.I.R.A.{" "}
            <span style={{ fontWeight: 400, color: "#666", fontSize: 14 }}>
              · Market Intelligence & Research Agent
            </span>
          </div>
          <div style={{ fontSize: 11, color: "#666" }}>{printDate}</div>
        </div>
        <div
          style={{
            marginTop: 6,
            fontSize: 12,
            color: "#444",
            display: "flex",
            gap: 14,
            flexWrap: "wrap",
          }}
        >
          {state.ticker && (
            <span>
              <strong>{state.exchange || "NYSE"} : {state.ticker}</strong>
              {state.companyName ? ` · ${state.companyName}` : ""}
            </span>
          )}
          {state.query && <span>“{state.query}”</span>}
        </div>
      </div>
      <DegradedBanner />
      <ProvenanceCard />
      <MarketCard />
      <CorrelationCard />
      <NarrativeCard />
      <FindingsCard />
      {state.report ? <ArticlesCard /> : null}
      {state.report ? <ToolBreakdownCard /> : null}
      <CitationsCard />
    </main>
  );
}

function DegradedBanner() {
  const { state } = useStream();
  const r = state.report;
  if (!r || !r.degraded) return null;
  const reason = (r.degradation_reason as string) ?? "Some data was unavailable.";
  return (
    <div
      style={{
        padding: "14px 18px",
        background: S.amberSoft,
        border: `1px solid ${S.amber}55`,
        borderRadius: 12,
        display: "flex",
        alignItems: "center",
        gap: 14,
      }}
    >
      <Tag color={S.amber} solid>
        Degraded
      </Tag>
      <span style={{ fontSize: 13, color: S.text, lineHeight: 1.5 }}>{reason}</span>
    </div>
  );
}

function ProvenanceCard() {
  const { state } = useStream();
  const r = state.report;
  if (!r) return null;
  const freshness = (r.data_freshness as Record<string, string | null> | null) ?? {};
  const tu = (r.token_usage as Record<string, number | string> | null) ?? {};
  const conf = (r.confidence as number | null) ?? null;
  const fmtTime = (iso: string | null | undefined) => {
    if (!iso) return "—";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "—";
    return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  };
  const items = [
    { label: "News freshness", value: fmtTime(freshness.newest_article_at as string | null) },
    { label: "Market data at", value: fmtTime(freshness.market_data_at as string | null) },
    { label: "EDGAR filing", value: fmtTime(freshness.edgar_filing_at as string | null) },
    { label: "Confidence", value: conf != null ? conf.toFixed(2) : "—" },
    { label: "Model", value: (tu.model as string) ?? "—" },
    {
      label: "Cost",
      value:
        typeof tu.cost_usd === "number"
          ? `$${(tu.cost_usd as number).toFixed(4)}`
          : "—",
    },
  ];
  return (
    <Section serial="00" name="Provenance" meta="signals · cost">
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(3, 1fr)",
          gap: 14,
        }}
      >
        {items.map((it) => (
          <div
            key={it.label}
            style={{
              padding: "12px 14px",
              background: S.surfaceHi,
              borderRadius: 10,
              display: "flex",
              flexDirection: "column",
              gap: 4,
            }}
          >
            <Eyebrow>{it.label}</Eyebrow>
            <span
              className="sp-mono"
              style={{ fontSize: 13, color: S.text, letterSpacing: -0.2 }}
            >
              {it.value}
            </span>
          </div>
        ))}
      </div>
    </Section>
  );
}

function ArticlesCard() {
  const { state } = useStream();
  const r = state.report;
  const dist = (r?.sentiment_distribution as Record<string, unknown> | undefined) ?? {};
  const articles = (dist.articles as Array<{
    title?: string;
    source?: string;
    url?: string;
    published_at?: string;
    sentiment?: string;
    sentiment_score?: number;
    rationale?: string;
  }>) ?? [];
  if (!articles.length) return null;
  const sentColor = (s?: string) =>
    s === "positive" ? S.mint : s === "negative" ? S.rose : S.text3;
  return (
    <Section
      serial="06"
      name="Articles analyzed"
      meta={`${articles.length} headline${articles.length === 1 ? "" : "s"} · per-article sentiment`}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {articles.map((a, i) => {
          const sc = a.sentiment_score ?? 0;
          const c = sentColor(a.sentiment);
          return (
            <div
              key={(a.url ?? "") + i}
              style={{
                padding: "14px 16px",
                background: S.surfaceHi,
                borderLeft: `3px solid ${c}`,
                borderRadius: 10,
                display: "flex",
                flexDirection: "column",
                gap: 8,
              }}
            >
              <div style={{ display: "flex", gap: 10, alignItems: "baseline" }}>
                <Tag color={c} solid>
                  {a.sentiment ?? "neutral"}
                </Tag>
                <span
                  className="sp-mono"
                  style={{ fontSize: 11, color: S.text3 }}
                >
                  {(sc >= 0 ? "+" : "") + sc.toFixed(2)}
                </span>
                <span style={{ flex: 1 }} />
                <span className="sp-mono" style={{ fontSize: 10, color: S.text3 }}>
                  {a.source ?? "—"}
                </span>
              </div>
              <a
                href={a.url}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  fontSize: 14,
                  fontWeight: 600,
                  color: S.text,
                  lineHeight: 1.35,
                  textDecoration: "none",
                  letterSpacing: -0.2,
                }}
              >
                {a.title ?? a.url ?? "untitled"}
              </a>
              {a.rationale ? (
                <div style={{ fontSize: 12, color: S.text2, lineHeight: 1.5 }}>
                  {a.rationale}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </Section>
  );
}

function ToolBreakdownCard() {
  const { state } = useStream();
  const r = state.report;
  const invs = (r?.tool_invocations as Array<{
    name?: string;
    input?: Record<string, unknown>;
    output_summary?: string;
    latency_ms?: number;
    status?: string;
  }>) ?? [];
  if (!invs.length) return null;
  return (
    <Section
      serial="07"
      name="Tools used"
      meta={`${invs.length} invocation${invs.length === 1 ? "" : "s"}`}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {invs.map((inv, i) => {
          const ok = (inv.status ?? "success") === "success";
          return (
            <div
              key={i}
              style={{
                padding: "12px 14px",
                background: S.surfaceHi,
                borderRadius: 10,
                display: "grid",
                gridTemplateColumns: "auto 1fr auto",
                gap: 14,
                alignItems: "center",
              }}
            >
              <Tag color={ok ? S.mint : S.rose} solid>
                {inv.name ?? "tool"}
              </Tag>
              <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                <span style={{ fontSize: 13, color: S.text, lineHeight: 1.4 }}>
                  {inv.output_summary ?? "—"}
                </span>
                {inv.input && Object.keys(inv.input).length ? (
                  <span
                    className="sp-mono"
                    style={{ fontSize: 10, color: S.text3 }}
                  >
                    {JSON.stringify(inv.input)}
                  </span>
                ) : null}
              </div>
              <span
                className="sp-mono"
                style={{ fontSize: 11, color: S.text3, whiteSpace: "nowrap" }}
              >
                {inv.latency_ms != null
                  ? inv.latency_ms >= 1000
                    ? `${(inv.latency_ms / 1000).toFixed(2)}s`
                    : `${inv.latency_ms}ms`
                  : "—"}
              </span>
            </div>
          );
        })}
      </div>
    </Section>
  );
}

function Section({
  serial,
  name,
  meta,
  children,
}: {
  serial: string;
  name: string;
  meta?: string;
  children?: React.ReactNode;
}) {
  return (
    <section
      style={{
        padding: 24,
        background: S.surface,
        border: `1px solid ${S.border}`,
        borderRadius: 16,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: 14,
          marginBottom: 22,
        }}
      >
        <Eyebrow serial={serial}>{name}</Eyebrow>
        <span style={{ flex: 1, height: 1, background: S.border }} />
        {meta && (
          <span className="sp-mono" style={{ fontSize: 10, color: S.text3 }}>
            {meta}
          </span>
        )}
      </div>
      {children}
    </section>
  );
}

function MarketCard() {
  const { state } = useStream();
  const m = state.market;
  return (
    <Section serial="01" name="Market snapshot" meta={m ? "yfinance · 142ms" : "waiting…"}>
      {!m ? (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 20 }}>
          {[...Array(5)].map((_, i) => (
            <div key={i} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <Skel w={60} h={8} />
              <Skel w={90} h={22} />
              <Skel w={50} h={8} />
            </div>
          ))}
        </div>
      ) : (
        <Fade in>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 20 }}>
            <Stat label="Price" value={m.price} delta={m.delta} sub="intraday" />
            <Stat label="P/E ttm" value={m.pe} sub={m.peSub} />
            <Stat label="52w range" value={m.range} sub={m.rangeSub} />
            <Stat label="Q1 revenue" value={m.q1} delta={m.q1Delta} sub="filed 23 apr" />
            <Stat label="Q4 revenue" value={m.q4} delta={m.q4Delta} sub="filed 13 feb" />
          </div>
          <div style={{ marginTop: 24, padding: "16px 4px 6px" }}>
            <Eyebrow style={{ marginBottom: 8 }}>Price · 30d · vs 30d mean</Eyebrow>
            <Spark data={m.spark} w={760} h={84} color={S.rose} fill />
            <div
              className="sp-mono"
              style={{
                display: "flex",
                justifyContent: "space-between",
                fontSize: 10,
                color: S.text3,
                marginTop: 6,
              }}
            >
              <span>15 apr</span>
              <span>μ $62.18 · σ $0.42</span>
              <span>15 may</span>
            </div>
          </div>
        </Fade>
      )}
    </Section>
  );
}

function CorrelationCard() {
  const { state } = useStream();
  const c = state.correlation;
  return (
    <Section serial="02" name="Correlation" meta={c ? "Pearson · 90d" : "waiting…"}>
      {!c ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {[...Array(4)].map((_, i) => (
            <div
              key={i}
              style={{
                display: "grid",
                gridTemplateColumns: "150px 1fr 64px",
                gap: 18,
                alignItems: "center",
              }}
            >
              <Skel w={120} h={10} />
              <Skel h={4} />
              <Skel w={40} h={10} />
            </div>
          ))}
        </div>
      ) : (
        <Fade in>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {c.map((r, i) => (
              <Fade key={r.label} in delay={i * 80}>
                <CorrBar label={r.label} value={r.value} />
              </Fade>
            ))}
          </div>
        </Fade>
      )}
      {state.reflectionFired && (
        <Fade in delay={120} style={{ marginTop: 18 }}>
          <div
            style={{
              padding: "14px 18px",
              background: S.amberSoft,
              border: `1px solid ${S.amber}3a`,
              borderRadius: 10,
              display: "flex",
              alignItems: "flex-start",
              gap: 12,
            }}
          >
            <Tag color={S.amber} solid>
              Reflection fired
            </Tag>
            <div style={{ fontSize: 13, color: S.text2, lineHeight: 1.5 }}>
              XLP sits just under the 0.95 idiosyncratic threshold — sector beta
              dominates, but does not fully explain. Sentiment was neutral-even, so a
              second research pass was commissioned for analyst commentary and the
              latest 10-Q.
            </div>
          </div>
        </Fade>
      )}
    </Section>
  );
}

function NarrativeCard() {
  const { state } = useStream();
  const hasAny = !!state.narrative.length;
  const text = state.narrative;
  // Highlight a notable phrase if present. Demo uses "sector-correlated
  // weakness"; for real reports, highlight the most-coral phrase among a
  // small library so the eye still has something to land on.
  const HL_CANDIDATES = [
    "sector-correlated weakness",
    "elasticity headwinds",
    "multiple compression",
    "margin compression",
    "earnings beat",
    "guidance cut",
    "execution risk",
    "regulatory tailwind",
  ];
  const hlPhrase = HL_CANDIDATES.find((p) => text.toLowerCase().includes(p)) ?? "";
  const hasHl = !!hlPhrase && text.toLowerCase().includes(hlPhrase);
  let parts: [string, string, string];
  if (hasHl) {
    const idx = text.toLowerCase().indexOf(hlPhrase);
    parts = [text.slice(0, idx), text.slice(idx, idx + hlPhrase.length), text.slice(idx + hlPhrase.length)];
  } else {
    parts = [text, "", ""];
  }
  return (
    <Section
      serial="03"
      name="Narrative"
      meta={(() => {
        if (!state.narrativeDone) return hasAny ? "streaming…" : "waiting…";
        const toks = Math.min(8000, state.events.length * 500 + state.narrative.length * 6);
        const tokStr = toks < 1000 ? `${toks}` : `${(toks / 1000).toFixed(1)}k`;
        return `synthesized · ${tokStr} tokens`;
      })()}
    >
      {!hasAny ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <Skel w="92%" h={20} />
          <Skel w="86%" h={20} />
          <Skel w="78%" h={20} />
          <Skel w="60%" h={20} />
        </div>
      ) : (
        <div
          style={{
            fontSize: 24,
            lineHeight: 1.4,
            color: S.text,
            fontWeight: 500,
            letterSpacing: -0.4,
            maxWidth: 740,
          }}
        >
          {parts[0]}
          {parts[1] && (
            <span
              style={{
                background: `linear-gradient(120deg, ${S.coralSoft} 0%, ${S.amberSoft} 100%)`,
                padding: "2px 6px",
                borderRadius: 4,
                color: S.coral,
                fontWeight: 600,
              }}
            >
              {parts[1]}
            </span>
          )}
          {parts[2]}
          {!state.narrativeDone && <span className="sp-caret" />}
        </div>
      )}

      {state.sentiment && (
        <Fade in style={{ marginTop: 24 }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 24,
              padding: "16px 20px",
              background: S.surfaceHi,
              borderRadius: 12,
            }}
          >
            <Eyebrow>Sentiment</Eyebrow>
            <div style={{ flex: 1, maxWidth: 360 }}>
              <SentimentBar
                pos={state.sentiment.pos}
                neu={state.sentiment.neu}
                neg={state.sentiment.neg}
              />
            </div>
            <Stat
              label="Score"
              value={state.sentiment.score.toFixed(2)}
              sub={`conf ${state.sentiment.conf.toFixed(2)}`}
              size={22}
              align="right"
              deltaColor={S.text3}
            />
          </div>
        </Fade>
      )}
    </Section>
  );
}

function FindingsCard() {
  const { state } = useStream();
  const f = state.findings;
  return (
    <Section
      serial="04"
      name="Key findings"
      meta={f.length ? `${f.length} of 3 observations` : "waiting…"}
    >
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 14 }}>
        {[0, 1, 2].map((i) => {
          const item: Finding | undefined = f[i];
          if (!item) return <SkelFinding key={i} />;
          const color = COLOR_MAP[item.color] ?? S.text;
          return (
            <Fade key={item.n} in>
              <div
                style={{
                  padding: 18,
                  background: S.surfaceHi,
                  border: `1px solid ${S.border}`,
                  borderTop: `2px solid ${color}`,
                  borderRadius: 12,
                  display: "flex",
                  flexDirection: "column",
                  gap: 10,
                }}
              >
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "flex-start",
                  }}
                >
                  <span
                    className="sp-num"
                    style={{
                      fontSize: 28,
                      fontWeight: 600,
                      color,
                      letterSpacing: -1,
                      lineHeight: 1,
                    }}
                  >
                    {item.n}
                  </span>
                  <Tag color={color}>finding</Tag>
                </div>
                <div
                  style={{
                    fontSize: 16,
                    fontWeight: 600,
                    color: S.text,
                    lineHeight: 1.3,
                    letterSpacing: -0.2,
                  }}
                >
                  {item.h}
                </div>
                <div style={{ fontSize: 13, color: S.text2, lineHeight: 1.5 }}>
                  {item.b}
                </div>
              </div>
            </Fade>
          );
        })}
      </div>
    </Section>
  );
}

function SkelFinding() {
  return (
    <div
      style={{
        padding: 18,
        background: S.surfaceHi,
        border: `1px solid ${S.border}`,
        borderTop: `2px solid ${S.border}`,
        borderRadius: 12,
        display: "flex",
        flexDirection: "column",
        gap: 10,
        minHeight: 168,
      }}
    >
      <Skel w={40} h={26} />
      <Skel w="80%" h={16} />
      <Skel w="100%" h={10} />
      <Skel w="92%" h={10} />
      <Skel w="60%" h={10} />
    </div>
  );
}

function CitationsCard() {
  const { state } = useStream();
  const c = state.citations;
  return (
    <Section
      serial="05"
      name="Sources"
      meta={c.length ? `${c.length} of 7 referenced` : "waiting…"}
    >
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
        {[0, 1, 2, 3].map((i) => {
          const item: Citation | undefined = c[i];
          if (!item) return <SkelCite key={i} />;
          return (
            <Fade key={item.title} in>
              <CiteChip
                source={item.source}
                title={item.title}
                when={item.when}
                color={COLOR_MAP[item.color] ?? S.azure}
              />
            </Fade>
          );
        })}
      </div>
    </Section>
  );
}

function SkelCite() {
  return (
    <div
      style={{
        padding: "14px 16px",
        background: S.surface,
        border: `1px solid ${S.border}`,
        borderRadius: 12,
        display: "flex",
        flexDirection: "column",
        gap: 10,
        minHeight: 84,
      }}
    >
      <Skel w={80} h={8} />
      <Skel w="92%" h={14} />
      <Skel w="60%" h={8} />
    </div>
  );
}

function SpectrumAgent() {
  return (
    <aside
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 20,
        position: "sticky",
        top: 80,
        alignSelf: "flex-start",
      }}
    >
      <NowExecuting />
      <ReasoningTimeline />
      <BudgetMeter />
    </aside>
  );
}

function NowExecuting() {
  const { state } = useStream();
  const tool: CurrentTool | null = state.currentTool;

  if (!tool && !state.done) {
    return (
      <div
        style={{
          padding: 22,
          background: S.surface,
          border: `1px solid ${S.border}`,
          borderRadius: 16,
          minHeight: 200,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 12,
        }}
      >
        <span
          className="sp-pulse"
          style={{ width: 10, height: 10, borderRadius: "50%", background: S.text4 }}
        />
        <Eyebrow>Agent · idle between tools</Eyebrow>
        <span className="sp-mono" style={{ fontSize: 10, color: S.text4 }}>
          planning the next step…
        </span>
      </div>
    );
  }

  if (state.done) {
    return (
      <div
        style={{
          padding: 22,
          background: S.surface,
          border: `1px solid ${S.mint}3a`,
          borderRadius: 16,
          position: "relative",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            bottom: 0,
            width: 3,
            background: S.mint,
          }}
        />
        <Eyebrow color={S.mint}>Filed · all done</Eyebrow>
        <div
          style={{
            fontSize: 22,
            fontWeight: 600,
            color: S.text,
            letterSpacing: -0.4,
            marginTop: 8,
          }}
        >
          Report ready.
        </div>
        <div style={{ fontSize: 13, color: S.text2, marginTop: 6, lineHeight: 1.5 }}>
          {(() => {
            const tools = state.events.filter((e) => e.kind === "tool").length;
            const refl = (state.reflectionFired ? 1 : 0) + (state.replanned ? 1 : 0);
            const toks = Math.min(8000, state.events.length * 500 + state.narrative.length * 6);
            const tokStr = toks < 1000 ? `${toks}` : `${(toks / 1000).toFixed(1)}k`;
            const plural = (n: number, w: string) => `${n} ${w}${n === 1 ? "" : "s"}`;
            const reflStr = refl === 0 ? "no reflections fired" : `${plural(refl, "reflection")} fired`;
            // state.filedAt already reads "Filed at 8:04 PM" — don't double-prefix.
            const filed = state.filedAt ? ` Dossier ${state.filedAt.toLowerCase()}.` : "";
            return `${plural(tools, "tool")} called, ${reflStr}, ${tokStr} tokens used.${filed}`;
          })()}
        </div>
      </div>
    );
  }

  const k = (tool && KIND_COLORS[tool.kind]) ?? KIND_COLORS.tool;
  return (
    <Fade in>
      <div
        style={{
          padding: 22,
          background: S.surface,
          border: `1px solid ${S.border}`,
          borderRadius: 16,
          position: "relative",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            bottom: 0,
            width: 3,
            background: k.c,
            boxShadow: `0 0 16px ${k.c}80`,
          }}
        />

        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            marginBottom: 12,
          }}
        >
          <span
            className="sp-pulse"
            style={{
              width: 8,
              height: 8,
              borderRadius: "50%",
              background: k.c,
              boxShadow: `0 0 8px ${k.c}`,
            }}
          />
          <Eyebrow color={k.c}>
            Now executing · step {String(state.events.length + 1).padStart(2, "0")}
          </Eyebrow>
          <span style={{ flex: 1 }} />
          <span className="sp-mono" style={{ fontSize: 10, color: S.text3 }}>
            live
          </span>
        </div>

        <div
          style={{
            fontSize: 20,
            fontWeight: 600,
            color: S.text,
            letterSpacing: -0.4,
            lineHeight: 1.25,
          }}
        >
          {tool?.name}
        </div>
        {tool?.sub && (
          <div style={{ fontSize: 13, color: S.text2, marginTop: 8, lineHeight: 1.5 }}>
            {tool.sub}
          </div>
        )}

        {tool?.input && (
          <div
            style={{
              marginTop: 14,
              padding: "10px 12px",
              background: "#1a1614",
              borderRadius: 8,
              fontFamily: S.fMono,
              fontSize: 11,
              color: "rgba(243,241,236,0.8)",
              lineHeight: 1.6,
              border: `1px solid rgba(0,0,0,0.1)`,
            }}
          >
            <div style={{ color: "rgba(243,241,236,0.4)" }}>{"// input"}</div>
            <div>
              {tool.input}
              <span className="sp-caret" />
            </div>
          </div>
        )}
      </div>
    </Fade>
  );
}

function ReasoningTimeline() {
  const { state } = useStream();
  const rows: Array<TimelineEvent & { future?: boolean }> = [...state.events];
  if (state.currentTool && !state.done) {
    rows.push({
      kind: state.currentTool.kind,
      title: state.currentTool.name,
      body: state.currentTool.sub ?? "running…",
      dur: "—",
      live: true,
    });
  }

  return (
    <div
      style={{
        background: S.surface,
        border: `1px solid ${S.border}`,
        borderRadius: 16,
        overflow: "hidden",
      }}
    >
      <div
        style={{
          padding: "20px 22px 14px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <div>
          <div
            style={{
              fontSize: 16,
              fontWeight: 600,
              color: S.text,
              letterSpacing: -0.2,
            }}
          >
            Reasoning
          </div>
          <div
            className="sp-mono"
            style={{ fontSize: 10, color: S.text3, letterSpacing: 0.4 }}
          >
            {rows.length} event{rows.length !== 1 ? "s" : ""} ·{" "}
            {state.reflectionFired ? "1 reflection · " : ""}
            {state.replanned ? "1 replan" : ""}
          </div>
        </div>
        <div style={{ display: "flex", gap: 4 }}>
          {(Object.entries(KIND_COLORS) as Array<[EventKind, { c: string; label: string }]>)
            .slice(0, 5)
            .map(([k, v]) => (
              <span
                key={k}
                title={v.label}
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  background: v.c,
                  boxShadow: `0 0 6px ${v.c}80`,
                }}
              />
            ))}
        </div>
      </div>

      <div
        style={{
          borderTop: `1px solid ${S.border}`,
          padding: "16px 22px 22px",
          maxHeight: 520,
          overflow: "auto",
        }}
      >
        {rows.length === 0 ? (
          <div
            style={{
              padding: "20px 0",
              display: "flex",
              flexDirection: "column",
              gap: 12,
              alignItems: "center",
              color: S.text3,
            }}
          >
            <Eyebrow>queued · waiting on first event</Eyebrow>
            <Skel w="80%" h={10} />
            <Skel w="60%" h={10} />
          </div>
        ) : (
          <div style={{ position: "relative" }}>
            <div
              style={{
                position: "absolute",
                left: 7,
                top: 12,
                bottom: 12,
                width: 1,
                background: S.border,
              }}
            />
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              {rows.map((e, i) => (
                <Fade key={i} in>
                  <EventRow {...e} done={!e.live && !e.future} />
                </Fade>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function EventRow({
  kind,
  title,
  body,
  dur,
  done,
  live,
  flag,
  future,
}: {
  kind: EventKind;
  title: string;
  body: string;
  dur: string;
  done?: boolean;
  live?: boolean;
  flag?: boolean;
  future?: boolean;
}) {
  const k = KIND_COLORS[kind] ?? KIND_COLORS.tool;
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "16px 1fr auto",
        gap: 14,
        alignItems: "flex-start",
        opacity: future ? 0.5 : 1,
      }}
    >
      <div style={{ paddingTop: 5, display: "flex", justifyContent: "center" }}>
        <span
          className={live ? "sp-pulse" : ""}
          style={{
            width: 10,
            height: 10,
            borderRadius: kind === "reflect" || kind === "replan" ? 2 : "50%",
            background: live ? k.c : done ? k.c : S.surface,
            border: `2px solid ${k.c}`,
            boxShadow: live ? `0 0 10px ${k.c}` : "none",
          }}
        />
      </div>
      <div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            marginBottom: 3,
          }}
        >
          <Tag color={k.c} style={{ padding: "1px 7px 1px", fontSize: 9 }}>
            {k.label}
          </Tag>
          {flag && (
            <Tag color={S.coral} solid style={{ fontSize: 9 }}>
              fired
            </Tag>
          )}
        </div>
        <div
          style={{
            fontSize: 13,
            fontWeight: 500,
            color: S.text,
            letterSpacing: -0.1,
            lineHeight: 1.3,
          }}
        >
          {title}
        </div>
        <div
          className="sp-mono"
          style={{ fontSize: 11, color: S.text3, marginTop: 2, lineHeight: 1.5 }}
        >
          {body}
          {live && <span className="sp-caret" />}
        </div>
      </div>
      <span
        className="sp-mono"
        style={{ fontSize: 10, color: S.text3, paddingTop: 6, whiteSpace: "nowrap" }}
      >
        {dur}
      </span>
    </div>
  );
}

function BudgetMeter() {
  const { state } = useStream();
  const r = state.report;
  const tu = (r?.token_usage as Record<string, number> | undefined) ?? {};
  const realTokens = (tu.total_tokens as number) ?? null;
  const realCost = (tu.cost_usd as number) ?? null;
  const realTc = ((r?.tool_invocations as unknown[]) ?? []).length || null;

  const tc = realTc ?? toolCallCount(state);
  const cost = realCost ?? currentCost(state);
  const tokens =
    realTokens ?? Math.min(4200, state.events.length * 500 + state.narrative.length * 6);
  const TOKEN_CAP = 8000;
  const COST_CAP = 0.05;
  const TOOL_CAP = 10;
  const pct = Math.round(
    ((Math.min(1, tokens / TOKEN_CAP) +
      Math.min(1, cost / COST_CAP) +
      Math.min(1, tc / TOOL_CAP)) /
      3) *
      100,
  );
  const meters = [
    {
      label: "Tokens",
      used: tokens < 1000 ? String(tokens) : (tokens / 1000).toFixed(1) + "k",
      cap: `${TOKEN_CAP / 1000}k`,
      pct: (tokens / TOKEN_CAP) * 100,
      color: S.azure,
    },
    {
      label: "Cost",
      used: `$${cost.toFixed(4)}`,
      cap: `$${COST_CAP.toFixed(2)}`,
      pct: (cost / COST_CAP) * 100,
      color: S.coral,
    },
    {
      label: "Tool calls",
      used: String(tc),
      cap: String(TOOL_CAP),
      pct: (tc / TOOL_CAP) * 100,
      color: S.mint,
    },
  ];
  return (
    <div
      style={{
        padding: 20,
        background: S.surface,
        border: `1px solid ${S.border}`,
        borderRadius: 16,
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          marginBottom: 14,
        }}
      >
        <div>
          <div
            style={{
              fontSize: 14,
              fontWeight: 600,
              color: S.text,
              letterSpacing: -0.2,
            }}
          >
            Budget
          </div>
          <div className="sp-mono" style={{ fontSize: 10, color: S.text3 }}>
            tokens · cost · time
          </div>
        </div>
        <span
          className="sp-num"
          style={{ fontSize: 22, fontWeight: 600, letterSpacing: -0.5 }}
        >
          {pct}
          <span style={{ color: S.text3, fontSize: 14 }}>%</span>
        </span>
      </div>

      {meters.map((m) => (
        <div key={m.label} style={{ marginBottom: 14 }}>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              marginBottom: 6,
            }}
          >
            <span className="sp-mono" style={{ fontSize: 11, color: S.text2 }}>
              {m.label}
            </span>
            <span className="sp-num" style={{ fontSize: 12, color: S.text }}>
              {m.used}
              <span style={{ color: S.text3 }}> / {m.cap}</span>
            </span>
          </div>
          <div
            style={{
              height: 4,
              background: S.surfaceHi,
              borderRadius: 2,
              overflow: "hidden",
            }}
          >
            <div
              style={{
                width: `${Math.min(100, m.pct)}%`,
                height: "100%",
                background: m.color,
                borderRadius: 2,
                boxShadow: `0 0 8px ${m.color}80`,
                transition: "width 300ms ease",
              }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

function ProcessingScreen({
  jobId,
  elapsed,
  query,
}: {
  jobId: string;
  elapsed: number;
  query: string;
}) {
  const sec = (elapsed / 1000).toFixed(1);
  const steps = [
    { label: "Plan", desc: "extract ticker · decompose query" },
    { label: "Tools", desc: "market data · news · correlation · peers" },
    { label: "Reflect", desc: "critic checks · re-plan if needed" },
    { label: "Synthesize", desc: "compose structured report · 3 findings" },
  ];
  // Estimate which step we're roughly in by elapsed time. Real analyses take
  // ~30-180s depending on tool latency. Pure UX cue — not exact.
  const stepIdx = Math.min(3, Math.floor(elapsed / 25000));
  return (
    <>
      <SpectrumGlobals />
      <div
        className="sp sp-page"
        style={{
          minHeight: "100vh",
          background: S.bg,
          position: "relative",
          overflow: "hidden",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <div
          style={{
            position: "absolute",
            top: -300,
            right: -200,
            width: 800,
            height: 800,
            background: `radial-gradient(circle, ${S.coralSoft} 0%, transparent 65%)`,
            pointerEvents: "none",
            zIndex: 0,
            opacity: 0.6,
          }}
        />
        <div
          style={{
            position: "absolute",
            bottom: -400,
            left: -200,
            width: 700,
            height: 700,
            background: `radial-gradient(circle, ${S.violetSoft} 0%, transparent 65%)`,
            pointerEvents: "none",
            zIndex: 0,
            opacity: 0.5,
          }}
        />

        <header
          style={{
            display: "flex",
            alignItems: "center",
            gap: 24,
            padding: "16px 40px",
            borderBottom: `1px solid ${S.border}`,
            backdropFilter: "blur(12px)",
            background: "rgba(247,245,240,0.78)",
            zIndex: 50,
          }}
        >
          <a href="/" style={{ display: "flex", alignItems: "center", gap: 12, textDecoration: "none", color: S.text }}>
            <div
              style={{
                width: 32,
                height: 32,
                borderRadius: 9,
                background: `linear-gradient(135deg, ${S.coral} 0%, ${S.violet} 100%)`,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "#fff",
                fontWeight: 700,
                fontSize: 14,
              }}
            >
              ✦
            </div>
            <div>
              <div style={{ fontSize: 14, fontWeight: 600, letterSpacing: -0.2 }}>M.I.R.A.</div>
              <div className="sp-mono" style={{ fontSize: 9, color: S.text3, letterSpacing: 0.6 }}>
                v1.0 · grok-4.3
              </div>
            </div>
          </a>
          <div style={{ flex: 1 }} />
          <Tag color={S.coral} dot>
            <span
              className="sp-pulse"
              style={{
                display: "inline-block",
                width: 6,
                height: 6,
                borderRadius: "50%",
                background: S.coral,
                marginRight: -2,
              }}
            />
            processing
          </Tag>
        </header>

        <div
          style={{
            position: "relative",
            zIndex: 1,
            flex: 1,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: 40,
          }}
        >
          <div
            style={{
              maxWidth: 720,
              width: "100%",
              padding: 40,
              background: S.surface,
              border: `1px solid ${S.border}`,
              borderRadius: 20,
              boxShadow: "0 20px 60px rgba(0,0,0,0.06)",
            }}
          >
            <Eyebrow>Case j-{jobId.slice(0, 6)} · live</Eyebrow>
            <div
              style={{
                fontSize: 38,
                fontWeight: 600,
                letterSpacing: "-0.03em",
                lineHeight: 1.1,
                color: S.text,
                margin: "16px 0 10px",
              }}
            >
              Analyzing…
            </div>
            {query ? (
              <div
                style={{
                  fontSize: 15,
                  color: S.text2,
                  lineHeight: 1.55,
                  padding: "14px 18px",
                  background: S.surfaceHi,
                  borderLeft: `3px solid ${S.coral}`,
                  borderRadius: 8,
                  marginBottom: 28,
                }}
              >
                {query}
              </div>
            ) : (
              <Skel w="80%" h={20} />
            )}

            <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 24 }}>
              {steps.map((step, i) => {
                const done = i < stepIdx;
                const active = i === stepIdx;
                const color = done ? S.mint : active ? S.coral : S.text4;
                return (
                  <div
                    key={step.label}
                    style={{
                      display: "grid",
                      gridTemplateColumns: "20px 1fr auto",
                      gap: 14,
                      alignItems: "center",
                      padding: "12px 14px",
                      background: active ? S.surfaceHi : "transparent",
                      borderRadius: 10,
                      transition: "background 200ms ease",
                    }}
                  >
                    <span
                      className={active ? "sp-pulse" : ""}
                      style={{
                        width: 12,
                        height: 12,
                        borderRadius: "50%",
                        background: done || active ? color : "transparent",
                        border: `2px solid ${color}`,
                        boxShadow: active ? `0 0 12px ${color}` : "none",
                      }}
                    />
                    <div>
                      <div
                        style={{
                          fontSize: 14,
                          fontWeight: 600,
                          color: active ? S.text : done ? S.text2 : S.text3,
                          letterSpacing: -0.1,
                        }}
                      >
                        {step.label}
                      </div>
                      <div style={{ fontSize: 12, color: S.text3, marginTop: 2 }}>{step.desc}</div>
                    </div>
                    <span
                      className="sp-mono"
                      style={{
                        fontSize: 10,
                        color: done ? S.mint : S.text4,
                        letterSpacing: 0.4,
                      }}
                    >
                      {done ? "DONE" : active ? "RUNNING" : "QUEUED"}
                    </span>
                  </div>
                );
              })}
            </div>

            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginTop: 28,
                paddingTop: 18,
                borderTop: `1px solid ${S.border}`,
              }}
            >
              <span className="sp-mono" style={{ fontSize: 11, color: S.text3 }}>
                ELAPSED {sec}s · typical 30–120s
              </span>
              <span className="sp-mono" style={{ fontSize: 11, color: S.text3 }}>
                polling /status every 2s
              </span>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

function SpectrumFooter() {
  const { state, controls } = useStream();
  return (
    <footer
      style={{
        borderTop: `1px solid ${S.border}`,
        padding: "20px 40px",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 20,
      }}
    >
      <div style={{ display: "flex", gap: 18, alignItems: "center" }}>
        <span
          className="sp-mono"
          style={{ fontSize: 10, color: S.text3, letterSpacing: 0.6 }}
        >
          {(() => {
            const tc = toolCallCount(state);
            const sec = (controls.elapsed / 1000).toFixed(1);
            if (state.done) {
              const filedShort = state.filedAt
                ? state.filedAt.replace(/^Filed at\s+/i, "").toUpperCase()
                : "READY";
              return `FILED ${filedShort} · ${tc} TOOL CALLS · LATENCY ${sec}s`;
            }
            return `STREAMING · ${sec}s ELAPSED · ${tc} TOOL CALLS`;
          })()}
        </span>
        <Tag color={state.done ? S.mint : S.coral} dot>
          {state.done ? "all circuits closed" : "live"}
        </Tag>
      </div>
    </footer>
  );
}
