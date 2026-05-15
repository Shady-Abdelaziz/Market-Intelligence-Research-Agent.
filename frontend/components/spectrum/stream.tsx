"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { S } from "./primitives";
import type { EventKind } from "./primitives";

export type CurrentTool = {
  kind: EventKind;
  name: string;
  input?: string;
  sub?: string;
};

export type TimelineEvent = {
  kind: EventKind;
  title: string;
  body: string;
  dur: string;
  flag?: boolean;
  live?: boolean;
};

export type Finding = {
  n: string;
  color: "coral" | "amber" | "azure" | "mint" | "violet" | "rose";
  h: string;
  b: string;
};

export type Citation = {
  source: string;
  title: string;
  when: string;
  color: "coral" | "amber" | "azure" | "mint" | "violet" | "rose";
};

export type MarketData = {
  price: string;
  delta: string;
  pe: string;
  peSub: string;
  range: string;
  rangeSub: string;
  q1: string;
  q1Delta: string;
  q4: string;
  q4Delta: string;
  spark: number[];
};

export type Sentiment = {
  pos: number;
  neu: number;
  neg: number;
  score: number;
  conf: number;
  label: string;
};

export type CorrelationRow = { label: string; value: number };

export type StreamState = {
  startedAt: number;
  events: TimelineEvent[];
  currentTool: CurrentTool | null;
  reflectionFired: boolean;
  replanned: boolean;
  market: MarketData | null;
  sentiment: Sentiment | null;
  correlation: CorrelationRow[] | null;
  narrative: string;
  narrativeDone: boolean;
  findings: Finding[];
  citations: Citation[];
  done: boolean;
  // identity / hero (set from real backend events; placeholders for demo mode)
  ticker: string;
  companyName: string;
  sector: string;
  marketCap: string;
  exchange: string;
  query: string;
  caseId: string;
  filedAt: string;
  failed: boolean;
  failedReason: string | null;
  // proactive monitoring metadata (set on monitor-fired analyses)
  alertTag: string | null;
  monitorTrigger: string | null;
};

export const TIMELINE_INITIAL: StreamState = {
  startedAt: 0,
  events: [],
  currentTool: null,
  reflectionFired: false,
  replanned: false,
  market: null,
  sentiment: null,
  correlation: null,
  narrative: "",
  narrativeDone: false,
  findings: [],
  citations: [],
  done: false,
  ticker: "",
  companyName: "",
  sector: "",
  marketCap: "",
  exchange: "",
  query: "",
  caseId: "",
  filedAt: "",
  failed: false,
  failedReason: null,
  alertTag: null,
  monitorTrigger: null,
};

const NARRATIVE_TEXT =
  "Coca-Cola is exhibiting sector-correlated weakness with idiosyncratic volume concerns. " +
  "North America volume declined 1.4% in the latest 10-Q while pricing rose 4.2% — " +
  "indicating elasticity headwinds that pricing power can mask only so long.";

function buildNarrativeStream(startAt: number, totalMs: number) {
  const tokens = NARRATIVE_TEXT.split(/(\s+)/).filter(Boolean);
  const n = tokens.length;
  const base = totalMs / n;
  const out: Array<{ at: number; token: string }> = [];
  let cursor = startAt;
  for (let i = 0; i < n; i++) {
    const tok = tokens[i];
    const jitter = (Math.sin(i * 1.7) + 1) * base * 0.3;
    let step = base + jitter * 0.4;
    if (/[.,—]$/.test(tok)) step += base * 3.5;
    out.push({ at: cursor, token: tok });
    cursor += step;
  }
  return out;
}

type TimelineStep = { at: number; apply: (s: StreamState) => StreamState };

function makeTimeline(): TimelineStep[] {
  const T: TimelineStep[] = [];

  // t=0 — seed the demo identity so the scripted preview matches the design
  T.push({
    at: 0,
    apply: (s) => ({
      ...s,
      ticker: "KO",
      companyName: "Coca-Cola Company.",
      sector: "Beverages — Non-Alcoholic",
      marketCap: "Market cap $268.4B",
      exchange: "NYSE",
      query: "Should I be worried about Coca-Cola's beverage volume trends going into summer?",
      caseId: "j-92a7f3",
      filedAt: "Filed at 14:08 GMT",
    }),
  });

  T.push({
    at: 200,
    apply: (s) => ({
      ...s,
      events: [
        ...s.events,
        {
          kind: "plan",
          title: "Plan · 3 tools + reflection guard",
          body: "extract → market · news · correlation",
          dur: "0.4s",
        },
      ],
    }),
  });

  T.push({
    at: 700,
    apply: (s) => ({
      ...s,
      currentTool: {
        kind: "tool",
        name: "market_data(KO)",
        input: '{ ticker: "KO" }',
        sub: "fetching quote and last 2 quarterly revenues from yfinance",
      },
    }),
  });

  T.push({
    at: 1500,
    apply: (s) => ({
      ...s,
      currentTool: null,
      market: {
        price: "$61.42",
        delta: "−0.6%",
        pe: "22.4",
        peSub: "sector 19.8",
        range: "54.0—66.2",
        rangeSub: "now 36th pct.",
        q1: "$11.30B",
        q1Delta: "+1.5%",
        q4: "$10.85B",
        q4Delta: "+8.2%",
        spark: [
          63.8, 64.1, 63.6, 63.9, 64.3, 63.7, 63.4, 63.0, 62.6, 62.8, 62.2, 61.8, 62.0,
          61.6, 61.42,
        ],
      },
      events: [
        ...s.events,
        {
          kind: "tool",
          title: "market_data(KO)",
          body: "$61.42 ↓0.6% · pe 22.4 · 52w 54.0–66.2",
          dur: "142ms",
        },
      ],
    }),
  });

  T.push({
    at: 1700,
    apply: (s) => ({
      ...s,
      currentTool: {
        kind: "tool",
        name: "news_sentiment(KO, n=5)",
        input: '{ ticker: "KO", n: 5 }',
        sub: "NewsAPI top 5 articles · per-article sentiment + Marketaux cross-check",
      },
    }),
  });

  T.push({
    at: 2600,
    apply: (s) => ({
      ...s,
      currentTool: null,
      sentiment: { pos: 1, neu: 3, neg: 1, score: -0.04, conf: 0.55, label: "soft" },
      events: [
        ...s.events,
        {
          kind: "tool",
          title: "news_sentiment(KO, n=5)",
          body: "pos 1 · neu 3 · neg 1 — soft",
          dur: "631ms",
        },
      ],
    }),
  });

  T.push({
    at: 2800,
    apply: (s) => ({
      ...s,
      currentTool: {
        kind: "tool",
        name: "correlation(KO, [SPX, XLP, PEP, MNST])",
        input: '{ window: "90d" }',
        sub: "Pearson over trailing 90 trading days vs benchmark, sector, peers",
      },
    }),
  });

  T.push({
    at: 3300,
    apply: (s) => ({
      ...s,
      currentTool: null,
      correlation: [
        { label: "vs. S&P 500", value: 0.81 },
        { label: "vs. XLP · sector", value: 0.94 },
        { label: "vs. PEP · peer", value: 0.71 },
        { label: "vs. MNST · peer", value: 0.34 },
      ],
      events: [
        ...s.events,
        {
          kind: "tool",
          title: "correlation(KO, [SPX, XLP, PEP, MNST])",
          body: "0.81 · 0.94 · 0.71 · 0.34",
          dur: "412ms",
        },
      ],
    }),
  });

  T.push({
    at: 3700,
    apply: (s) => ({
      ...s,
      reflectionFired: true,
      events: [
        ...s.events,
        {
          kind: "reflect",
          title: "critic · neutral_even fired",
          body: "|pos − neg| = 0 and neu ≥ 3",
          dur: "0.5s",
          flag: true,
        },
      ],
    }),
  });

  T.push({
    at: 4100,
    apply: (s) => ({
      ...s,
      replanned: true,
      events: [
        ...s.events,
        {
          kind: "replan",
          title: "Re-plan · +2 tools",
          body: "+ edgar · + news(analyst)",
          dur: "0.2s",
        },
      ],
    }),
  });

  T.push({
    at: 4400,
    apply: (s) => ({
      ...s,
      currentTool: {
        kind: "tool",
        name: "edgar(KO)",
        input: '{ filings: ["10-Q", "8-K"], since: "30d" }',
        sub: "SEC EDGAR — fetching last 30-day filings (proper User-Agent set)",
      },
    }),
  });

  T.push({
    at: 5300,
    apply: (s) => ({
      ...s,
      currentTool: null,
      events: [
        ...s.events,
        {
          kind: "tool",
          title: "edgar(KO)",
          body: "10-Q apr 23 · NA vol −1.4% · pricing +4.2%",
          dur: "880ms",
        },
      ],
    }),
  });

  T.push({
    at: 5500,
    apply: (s) => ({
      ...s,
      currentTool: {
        kind: "tool",
        name: 'news_sentiment(KO, "analyst commentary")',
        input: '{ query: "analyst commentary", recency: "7d" }',
        sub: "expanding research — fetching analyst notes after reflection",
      },
    }),
  });

  T.push({
    at: 6100,
    apply: (s) => ({
      ...s,
      currentTool: null,
      sentiment: { pos: 3, neu: 4, neg: 1, score: -0.12, conf: 0.66, label: "cautious" },
      events: [
        ...s.events,
        {
          kind: "tool",
          title: 'news_sentiment(KO, "analyst")',
          body: "pos 2 · neu 1 — RBC outperform · Citi neutral",
          dur: "522ms",
        },
      ],
    }),
  });

  T.push({
    at: 6300,
    apply: (s) => ({
      ...s,
      currentTool: {
        kind: "synth",
        name: "synthesize report",
        input: '{ model: "grok-4.3", stream: true }',
        sub: "composing structured report — streaming tokens →",
      },
      events: [
        ...s.events,
        {
          kind: "synth",
          title: "synthesize report",
          body: "streaming tokens to report panel",
          dur: "now",
          live: true,
        },
      ],
    }),
  });

  const narrStart = 6500;
  const narrEnd = 13200;
  const narrEvents = buildNarrativeStream(narrStart, narrEnd - narrStart);
  let narrAcc = "";
  for (const ne of narrEvents) {
    narrAcc += ne.token;
    const snapshot = narrAcc;
    T.push({ at: ne.at, apply: (s) => ({ ...s, narrative: snapshot }) });
  }

  T.push({
    at: 13400,
    apply: (s) => ({
      ...s,
      narrativeDone: true,
      findings: [
        ...s.findings,
        {
          n: "01",
          color: "coral",
          h: "Volume decline despite pricing power",
          b: "NA unit case volume −1.4% YoY (Q1) while net pricing +4.2% — masks softening demand. Watch elasticity into summer as the comp base hardens.",
        },
      ],
    }),
  });
  T.push({
    at: 13700,
    apply: (s) => ({
      ...s,
      findings: [
        ...s.findings,
        {
          n: "02",
          color: "amber",
          h: "Sector beta dominates near-term",
          b: "XLP correlation at 0.94. KO is moving with the staples cohort more than on company-specific catalysts. Idiosyncratic alpha is thin.",
        },
      ],
    }),
  });
  T.push({
    at: 14000,
    apply: (s) => ({
      ...s,
      findings: [
        ...s.findings,
        {
          n: "03",
          color: "azure",
          h: "Analyst tone constructive despite softness",
          b: "RBC reiterates Outperform ($72 PT); Citi Neutral; Morgan Stanley flags pricing offset. Volume risk acknowledged but not yet priced.",
        },
      ],
    }),
  });

  T.push({
    at: 14400,
    apply: (s) => ({
      ...s,
      citations: [
        ...s.citations,
        {
          source: "SEC · EDGAR",
          title: "KO Form 10-Q — Q1 2026",
          when: "23 apr",
          color: "azure",
        },
      ],
    }),
  });
  T.push({
    at: 14600,
    apply: (s) => ({
      ...s,
      citations: [
        ...s.citations,
        {
          source: "Reuters",
          title: "Coca-Cola lifts annual sales forecast on price hikes",
          when: "30 apr",
          color: "mint",
        },
      ],
    }),
  });
  T.push({
    at: 14800,
    apply: (s) => ({
      ...s,
      citations: [
        ...s.citations,
        {
          source: "WSJ",
          title: "Volume softness flagged as pricing nears ceiling",
          when: "02 may",
          color: "coral",
        },
      ],
    }),
  });
  T.push({
    at: 15000,
    apply: (s) => ({
      ...s,
      citations: [
        ...s.citations,
        {
          source: "RBC CM",
          title: "Reiterating Outperform, raising PT to $72",
          when: "10 may",
          color: "violet",
        },
      ],
    }),
  });

  T.push({
    at: 15400,
    apply: (s) => ({
      ...s,
      done: true,
      currentTool: null,
      events: [
        ...s.events.map((e) => (e.live ? { ...e, live: false, dur: "8.1s" } : e)),
        {
          kind: "done",
          title: "Filed.",
          body: "4.2k tokens · $0.018 · cache hit 31%",
          dur: "15.4s",
        },
      ],
    }),
  });

  return T;
}

export const TIMELINE = makeTimeline();
export const TIMELINE_DURATION = 15800;

export type StreamControlsValue = {
  replay: () => void;
  togglePlay: () => void;
  playing: boolean;
  elapsed: number;
  done: boolean;
};

export function useAgentStream(timeline = TIMELINE): {
  state: StreamState;
  controls: StreamControlsValue;
} {
  const [state, setState] = useState<StreamState>(TIMELINE_INITIAL);
  const [playing, setPlaying] = useState(true);
  const [step, setStep] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const startRef = useRef(performance.now());

  useEffect(() => {
    if (!playing) return;
    if (step >= timeline.length) return;
    const next = timeline[step];
    const targetTime = next.at;
    const now = performance.now() - startRef.current;
    const delay = Math.max(0, targetTime - now);
    const t = setTimeout(() => {
      setState((prev) => next.apply(prev));
      setStep((s) => s + 1);
    }, delay);
    return () => clearTimeout(t);
  }, [playing, step, timeline]);

  useEffect(() => {
    if (!playing) return;
    if (step >= timeline.length) return;
    const id = setInterval(() => {
      setElapsed(Math.min(TIMELINE_DURATION, performance.now() - startRef.current));
    }, 60);
    return () => clearInterval(id);
  }, [playing, step, timeline.length]);

  const replay = useCallback(() => {
    setState(TIMELINE_INITIAL);
    setStep(0);
    setElapsed(0);
    startRef.current = performance.now();
    setPlaying(true);
  }, []);

  const togglePlay = useCallback(() => {
    setPlaying((p) => {
      if (p) return false;
      startRef.current = performance.now() - elapsed;
      return true;
    });
  }, [elapsed]);

  return {
    state,
    controls: { replay, togglePlay, playing, elapsed, done: step >= timeline.length },
  };
}

// ============================================================================
//  REAL AGENT STREAM — subscribes to /status/{jobId}/stream and translates
//  real backend SSE events into the same StreamState shape the scripted demo
//  uses. The visual components don't care which hook produced the state.
// ============================================================================

type ColorName = "coral" | "amber" | "azure" | "mint" | "violet" | "rose";
const FINDING_COLORS: ColorName[] = ["coral", "amber", "azure"];
const CITATION_COLORS: ColorName[] = ["azure", "mint", "coral", "violet", "amber", "rose"];

function fmtMoney(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  if (Math.abs(n) >= 1_000_000_000_000) return `$${(n / 1e12).toFixed(2)}T`;
  if (Math.abs(n) >= 1_000_000_000) return `$${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1_000_000) return `$${(n / 1e6).toFixed(2)}M`;
  return `$${n.toFixed(2)}`;
}

function fmtPct(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  const s = n >= 0 ? "+" : "−";
  return `${s}${Math.abs(n).toFixed(2)}%`;
}

function fmtQuarterRev(q: { quarter?: string; revenue_usd?: number } | undefined): {
  q: string;
  rev: string;
} {
  if (!q) return { q: "—", rev: "—" };
  return { q: q.quarter ?? "—", rev: fmtMoney(q.revenue_usd ?? 0) };
}

function quarterDelta(
  q?: { revenue_usd?: number },
  prev?: { revenue_usd?: number },
): string | undefined {
  if (!q?.revenue_usd || !prev?.revenue_usd) return undefined;
  const d = ((q.revenue_usd - prev.revenue_usd) / prev.revenue_usd) * 100;
  return fmtPct(d);
}

function buildMarketFromTool(data: Record<string, unknown>): MarketData {
  const last2 = (data.last_two_quarterly_revenues as Array<{
    quarter?: string;
    revenue_usd?: number;
  }>) ?? [];
  const q1 = fmtQuarterRev(last2[0]);
  const q4 = fmtQuarterRev(last2[1]);
  return {
    price: fmtMoney(data.price as number | null),
    delta: fmtPct(data.daily_change_pct as number | null),
    pe:
      typeof data.pe_ratio === "number" && Number.isFinite(data.pe_ratio)
        ? (data.pe_ratio as number).toFixed(1)
        : "—",
    peSub: "trailing",
    range: (() => {
      const lo = data.fifty_two_week_low as number | null;
      const hi = data.fifty_two_week_high as number | null;
      if (lo == null || hi == null) return "—";
      return `${lo.toFixed(1)}—${hi.toFixed(1)}`;
    })(),
    rangeSub: "52w",
    q1: q1.rev,
    q1Delta: quarterDelta(last2[0], last2[1]) ?? "",
    q4: q4.rev,
    q4Delta: "",
    spark: [],
  };
}

function buildCorrelationFromTool(
  data: Record<string, unknown>,
): CorrelationRow[] {
  const rows: CorrelationRow[] = [];
  const sp = data.vs_sp500 as number | undefined;
  const sec = data.vs_sector_etf as number | undefined;
  const secSym = (data.sector_etf_symbol as string | undefined) ?? "SECTOR";
  const peers = (data.vs_peers as Record<string, number> | undefined) ?? {};
  if (typeof sp === "number") rows.push({ label: "vs. S&P 500", value: sp });
  if (typeof sec === "number")
    rows.push({ label: `vs. ${secSym} · sector`, value: sec });
  for (const [peer, v] of Object.entries(peers)) {
    if (typeof v === "number") rows.push({ label: `vs. ${peer} · peer`, value: v });
  }
  return rows;
}

function buildSentimentFromTool(data: Record<string, unknown>): Sentiment {
  const dist = (data.distribution as Record<string, number> | undefined) ?? {};
  const score = (data.overall_score as number | null) ?? 0;
  const label =
    score > 0.2 ? "positive" : score < -0.2 ? "negative" : "neutral";
  return {
    pos: dist.positive ?? 0,
    neu: dist.neutral ?? 0,
    neg: dist.negative ?? 0,
    score,
    conf: (data.confidence as number | null) ?? 0.8,
    label,
  };
}

function relTime(iso: string | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString(undefined, { month: "short", day: "numeric" }).toLowerCase();
}

function sourceFromUrl(u: string): string {
  try {
    return new URL(u).hostname.replace(/^www\./, "").split(".")[0].toUpperCase();
  } catch {
    return "WEB";
  }
}

// Parse partial streaming JSON for the analysis_summary value.
// Returns the accumulated text inside "analysis_summary":"…" (still streaming
// if the closing quote hasn't arrived yet).
function extractStreamingSummary(buf: string): string | null {
  const key = '"analysis_summary"';
  const idx = buf.indexOf(key);
  if (idx === -1) return null;
  let i = idx + key.length;
  while (i < buf.length && /[\s:]/.test(buf[i])) i++;
  if (buf[i] !== '"') return null;
  i++;
  let out = "";
  while (i < buf.length) {
    const ch = buf[i];
    if (ch === "\\" && i + 1 < buf.length) {
      const n = buf[i + 1];
      out += n === "n" ? "\n" : n === "t" ? "\t" : n;
      i += 2;
      continue;
    }
    if (ch === '"') return out;
    out += ch;
    i++;
  }
  return out;
}

export function useRealAgentStream(
  jobId: string | null,
  apiBase?: string,
): { state: StreamState; controls: StreamControlsValue } {
  const base =
    apiBase ??
    (typeof process !== "undefined"
      ? process.env.NEXT_PUBLIC_API_BASE_URL
      : undefined) ??
    "http://localhost:8000";
  const [state, setState] = useState<StreamState>({
    ...TIMELINE_INITIAL,
    caseId: jobId ? `j-${jobId.slice(0, 6)}` : "",
  });
  const startRef = useRef(performance.now());
  const [elapsed, setElapsed] = useState(0);
  const synthBufRef = useRef<string>("");
  const eventCountRef = useRef(0);
  const stepStartRef = useRef<Record<string, number>>({});

  const apply = useCallback((m: (s: StreamState) => StreamState) => setState(m), []);

  // Tick elapsed for the controls progress bar
  useEffect(() => {
    const id = setInterval(() => {
      setElapsed(performance.now() - startRef.current);
    }, 100);
    return () => clearInterval(id);
  }, []);

  // Subscribe to SSE
  useEffect(() => {
    if (!jobId) return;
    // Hydrate from the snapshot endpoint first (handles late navigation /
    // page reloads where events have already been emitted)
    let cancelled = false;
    void (async () => {
      try {
        const r = await fetch(`${base}/status/${jobId}`);
        if (!r.ok) return;
        const snap = await r.json();
        if (cancelled) return;
        if (snap?.report) {
          // Replay terminal state directly from the persisted report
          apply((s) => mergeReportIntoState(s, snap.report));
        } else if (snap?.query) {
          apply((s) => ({ ...s, query: snap.query }));
        }
      } catch {
        /* offline / 404 — let SSE drive the state */
      }
    })();

    const es = new EventSource(`${base}/status/${jobId}/stream`);
    const types = [
      "ticker_resolved",
      "ticker_resolution_failed",
      "planner_decision",
      "tool_start",
      "tool_end",
      "reflection_thought",
      "replan",
      "synthesis_token",
      "done",
      "error",
    ];

    const handler = (type: string) => (ev: MessageEvent) => {
      let data: Record<string, unknown> = {};
      try {
        data = JSON.parse(ev.data);
      } catch {
        return;
      }
      apply((s) => reduce(s, type, data, synthBufRef, eventCountRef, stepStartRef));
      if (type === "done" || type === "error") {
        es.close();
      }
    };

    for (const t of types) es.addEventListener(t, handler(t) as EventListener);
    es.onerror = () => {
      /* EventSource auto-reconnects; if the backend isn't there we still show
         whatever the snapshot fetch hydrated. */
    };

    return () => {
      cancelled = true;
      es.close();
    };
  }, [jobId, base, apply]);

  const replay = useCallback(() => {
    setState({
      ...TIMELINE_INITIAL,
      caseId: jobId ? `j-${jobId.slice(0, 6)}` : "",
    });
    synthBufRef.current = "";
    eventCountRef.current = 0;
    stepStartRef.current = {};
    startRef.current = performance.now();
    setElapsed(0);
    // Re-fetch snapshot so the report comes back if it was already filed
    if (jobId) {
      void fetch(`${base}/status/${jobId}`)
        .then((r) => (r.ok ? r.json() : null))
        .then((snap) => {
          if (snap?.report) {
            setState((s) => mergeReportIntoState(s, snap.report));
          }
        })
        .catch(() => {});
    }
  }, [jobId, base]);

  const togglePlay = useCallback(() => {
    // Real streams can't be paused — the backend is shipping events live.
    // No-op to keep the StreamControls UI consistent.
  }, []);

  return {
    state,
    controls: {
      replay,
      togglePlay,
      playing: !state.done,
      elapsed,
      done: state.done,
    },
  };
}

function reduce(
  s: StreamState,
  type: string,
  data: Record<string, unknown>,
  synthBufRef: { current: string },
  eventCountRef: { current: number },
  stepStartRef: { current: Record<string, number> },
): StreamState {
  switch (type) {
    case "ticker_resolved": {
      const ticker = (data.ticker as string) ?? s.ticker;
      const name = (data.company_name as string) ?? ticker;
      return {
        ...s,
        ticker,
        companyName: name.endsWith(".") ? name : `${name}.`,
        exchange: (data.exchange as string) ?? "NYSE",
      };
    }
    case "ticker_resolution_failed": {
      return {
        ...s,
        failed: true,
        failedReason: (data.reason as string) ?? "ticker_unknown",
      };
    }
    case "planner_decision": {
      const tools = (data.tools as string[]) ?? [];
      const plan = (data.plan as string) ?? "plan";
      const pass = (data.pass as number) ?? 0;
      eventCountRef.current += 1;
      return {
        ...s,
        events: [
          ...s.events,
          {
            kind: pass === 0 ? "plan" : "replan",
            title:
              pass === 0
                ? `Plan · ${tools.length} tool${tools.length === 1 ? "" : "s"}`
                : `Re-plan · ${tools.length} tool${tools.length === 1 ? "" : "s"}`,
            body: plan,
            dur: "—",
          },
        ],
        replanned: pass > 0 ? true : s.replanned,
      };
    }
    case "tool_start": {
      const name = (data.tool as string) ?? "tool";
      const input = data.input as Record<string, unknown> | undefined;
      stepStartRef.current[name] = performance.now();
      return {
        ...s,
        currentTool: {
          kind: name === "edgar_filings" ? "tool" : "tool",
          name,
          input: input ? JSON.stringify(input) : undefined,
          sub: `running ${name}…`,
        },
      };
    }
    case "tool_end": {
      const name = (data.tool as string) ?? "tool";
      const summary = (data.output_summary as string) ?? "";
      const latency = (data.latency_ms as number) ?? 0;
      const status = (data.status as string) ?? "success";
      const tdata = data.data as Record<string, unknown> | null;

      let next: StreamState = {
        ...s,
        currentTool: null,
        events: [
          ...s.events,
          {
            kind: "tool",
            title: name,
            body: summary,
            dur: latency >= 1000 ? `${(latency / 1000).toFixed(2)}s` : `${latency}ms`,
          },
        ],
      };

      if (status !== "success" || !tdata) return next;

      if (name === "market_data") {
        next = {
          ...next,
          market: buildMarketFromTool(tdata),
          // also seed identity if not already set
          ticker: s.ticker || ((tdata.ticker as string) ?? ""),
          companyName:
            s.companyName ||
            ((tdata.company_name as string)
              ? `${tdata.company_name}.`
              : ((tdata.ticker as string) ?? "")),
          sector: s.sector || ((tdata.sector as string) ?? ""),
        };
      } else if (name === "correlation") {
        next = { ...next, correlation: buildCorrelationFromTool(tdata) };
      } else if (name === "news_sentiment") {
        next = { ...next, sentiment: buildSentimentFromTool(tdata) };
      } else if (name === "peer_news") {
        // Peer news is a separate signal (a competitor's articles) — surface
        // it as a sentiment overlay only if we don't already have primary
        // sentiment, otherwise leave the primary card untouched. The
        // timeline event still shows the peer ticker.
        if (!next.sentiment) next = { ...next, sentiment: buildSentimentFromTool(tdata) };
      }
      return next;
    }
    case "reflection_thought": {
      const fired = data.fired as boolean;
      const trig = (data.trigger_evaluated as string) ?? "";
      const reason = (data.reasoning as string) ?? "";
      if (!fired) return s;
      return {
        ...s,
        reflectionFired: true,
        events: [
          ...s.events,
          {
            kind: "reflect",
            title: `critic · ${trig} fired`,
            body: reason,
            dur: "—",
            flag: true,
          },
        ],
      };
    }
    case "replan": {
      const triggers = (data.triggers_fired as string[]) ?? [];
      return {
        ...s,
        replanned: true,
        events: [
          ...s.events,
          {
            kind: "replan",
            title: `Re-plan · ${triggers.length} trigger${triggers.length === 1 ? "" : "s"}`,
            body: triggers.join(" · "),
            dur: "—",
          },
        ],
      };
    }
    case "synthesis_token": {
      const tok = (data.token as string) ?? "";
      synthBufRef.current += tok;
      const summary = extractStreamingSummary(synthBufRef.current);
      if (summary == null) return s;
      return { ...s, narrative: summary };
    }
    case "done": {
      const report = data.report as Record<string, unknown> | undefined;
      if (!report) return { ...s, done: true, narrativeDone: true };
      return mergeReportIntoState(s, report);
    }
    case "error": {
      return {
        ...s,
        done: true,
        failed: true,
        failedReason: (data.message as string) ?? "error",
        narrativeDone: true,
      };
    }
  }
  return s;
}

function mergeReportIntoState(
  s: StreamState,
  report: Record<string, unknown>,
): StreamState {
  const ms = report.market_snapshot as Record<string, unknown> | undefined;
  const corr = report.correlation_analysis as Record<string, unknown> | undefined;
  const sd = report.sentiment_distribution as Record<string, unknown> | undefined;
  const ticker = (report.company_ticker as string) ?? s.ticker;
  const name = (report.company_name as string) ?? ticker;
  const findingsArr = (report.key_findings as string[]) ?? [];
  const citationsArr = (report.citation_sources as string[]) ?? [];
  const findings: Finding[] = findingsArr.slice(0, 3).map((b, i) => ({
    n: String(i + 1).padStart(2, "0"),
    color: FINDING_COLORS[i % FINDING_COLORS.length],
    h: b.split(/[.!?]/)[0].slice(0, 80) || b.slice(0, 80),
    b,
  }));
  const articlesArr = sd?.articles as
    | Array<{ url: string; title?: string; source?: string; published_at?: string }>
    | undefined;
  const citations: Citation[] = citationsArr.slice(0, 4).map((url, i) => {
    const meta = articlesArr?.find((a) => a.url === url);
    return {
      source: meta?.source || sourceFromUrl(url),
      title: meta?.title || url,
      when: relTime(meta?.published_at),
      color: CITATION_COLORS[i % CITATION_COLORS.length],
    };
  });
  const generatedAt = report.generated_at as string | undefined;
  const filedAt = generatedAt
    ? `Filed at ${new Date(generatedAt).toLocaleTimeString(undefined, {
        hour: "2-digit",
        minute: "2-digit",
      })}`
    : s.filedAt;

  return {
    ...s,
    done: true,
    ticker,
    companyName: name.endsWith(".") ? name : `${name}.`,
    sector: s.sector || (ms?.sector as string) || "",
    marketCap: ms?.market_cap
      ? `Market cap ${fmtMoney(ms.market_cap as number)}`
      : s.marketCap,
    market: ms ? buildMarketFromTool(ms) : s.market,
    correlation: corr ? buildCorrelationFromTool(corr) : s.correlation,
    sentiment: sd
      ? buildSentimentFromTool({
          distribution: sd,
          overall_score: report.sentiment_score,
          confidence: report.confidence,
        })
      : s.sentiment,
    narrative: (report.analysis_summary as string) ?? s.narrative,
    narrativeDone: true,
    findings,
    citations,
    filedAt,
    alertTag: (report.alert_tag as string | null) ?? s.alertTag,
    monitorTrigger:
      (report.monitor_trigger as string | null) ?? s.monitorTrigger,
  };
}

export function StreamControls({ controls }: { controls: StreamControlsValue }) {
  const pct = Math.min(100, (controls.elapsed / TIMELINE_DURATION) * 100);
  return (
    <div
      style={{
        position: "fixed",
        right: 24,
        bottom: 24,
        zIndex: 100,
        display: "flex",
        alignItems: "center",
        gap: 12,
        padding: "10px 14px",
        background: "rgba(247,245,240,0.92)",
        backdropFilter: "blur(12px)",
        border: `1px solid ${S.border}`,
        borderRadius: 100,
        boxShadow: "0 8px 32px rgba(0,0,0,0.08)",
      }}
    >
      <button
        onClick={controls.togglePlay}
        style={{
          width: 32,
          height: 32,
          borderRadius: "50%",
          border: "none",
          background: S.coral,
          color: "#fff",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          cursor: "pointer",
          fontSize: 12,
          fontWeight: 700,
        }}
        title={controls.playing ? "pause" : "play"}
      >
        {controls.playing ? "❚❚" : "▶"}
      </button>
      <div style={{ width: 180 }}>
        <div
          className="sp-mono"
          style={{
            fontSize: 10,
            color: S.text3,
            display: "flex",
            justifyContent: "space-between",
            marginBottom: 4,
          }}
        >
          <span>{(controls.elapsed / 1000).toFixed(1)}s</span>
          <span>{controls.done ? "done" : "streaming"}</span>
          <span>{(TIMELINE_DURATION / 1000).toFixed(1)}s</span>
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
              width: `${pct}%`,
              height: "100%",
              background: `linear-gradient(90deg, ${S.coral}, ${S.violet})`,
              borderRadius: 2,
              transition: "width 60ms linear",
            }}
          />
        </div>
      </div>
      <button
        onClick={controls.replay}
        style={{
          padding: "6px 14px",
          border: `1px solid ${S.border}`,
          background: S.surface,
          color: S.text,
          fontSize: 12,
          fontWeight: 500,
          borderRadius: 100,
          cursor: "pointer",
          fontFamily: S.fSans,
        }}
      >
        ↻ Replay
      </button>
    </div>
  );
}
