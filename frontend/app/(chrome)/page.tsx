"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { postAnalyze } from "@/lib/api";

interface Sample {
  ticker: string;
  company: string;
  prompt: string;
}

const SAMPLES: Sample[] = [
  { ticker: "TSLA", company: "Tesla, Inc.", prompt: "Analyze the near-term prospects of Tesla, Inc. (TSLA)." },
  { ticker: "AAPL", company: "Apple Inc.", prompt: "What's the outlook for Apple (AAPL) given recent news?" },
  { ticker: "KO", company: "Coca-Cola Co.", prompt: "Should I be concerned about Coca-Cola (KO) right now?" },
  { ticker: "NVDA", company: "NVIDIA Corp.", prompt: "Deep dive on NVDA fundamentals and sentiment." },
];

export default function SubmitPage() {
  return (
    <Suspense fallback={null}>
      <SubmitPageInner />
    </Suspense>
  );
}

function SubmitPageInner() {
  const router = useRouter();
  const sp = useSearchParams();
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const q = sp.get("q");
    if (q) setQuery(q);
  }, [sp]);

  async function submit(q: string) {
    setErr(null);
    setLoading(true);
    try {
      const { job_id } = await postAnalyze(q);
      router.push(`/jobs/${job_id}`);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Failed to submit");
      setLoading(false);
    }
  }

  return (
    <main className="container">
      <section className="hero">
        <div className="h-row">
          <span className="badge">Autonomous equity research</span>
          <span>v1.0</span>
          <span className="pipe">·</span>
          <span>LangGraph · grok-4.3 · ≤ 10 tool calls</span>
        </div>
        <h1 className="headline">Plan. Probe. Synthesize.</h1>
        <p className="subhead">
          Ask about a public equity in natural language. MIRA plans the research, calls market,
          news and correlation tools, reflects on the evidence, and files a structured report
          while it streams.
        </p>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (query.trim()) submit(query.trim());
          }}
          className="submit-card"
        >
          <div className="eyebrow" style={{ marginBottom: 8 }}>Operator&apos;s brief</div>
          <textarea
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder='e.g. "Analyze the near-term prospects of Tesla, Inc. (TSLA)."'
            rows={3}
          />
          <div className="submit-foot">
            <span className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>
              natural language · any US equity
            </span>
            <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
              {err && <span className="submit-error">{err}</span>}
              <button type="submit" className="btn" disabled={loading || !query.trim()}>
                {loading ? "Submitting…" : "Run analysis →"}
              </button>
            </div>
          </div>
        </form>
      </section>

      <section style={{ marginTop: 12 }}>
        <div className="eyebrow" style={{ marginBottom: 14 }}>Try a sample</div>
        <div className="samples">
          {SAMPLES.map((s) => (
            <button
              key={s.ticker}
              className="sample"
              onClick={() => submit(s.prompt)}
              disabled={loading}
            >
              <span className="tk">NASDAQ · {s.ticker}</span>
              <span className="co">{s.company}</span>
              <span className="pr">{s.prompt}</span>
              <span className="mono" style={{ fontSize: 10, color: "var(--primary)", marginTop: 4 }}>
                RUN ANALYSIS →
              </span>
            </button>
          ))}
        </div>
      </section>

      <section className="section">
        <header className="section-head">
          <span className="num">Pipeline</span>
          <h2>Four stages, one report.</h2>
          <p>The agent plans the call, runs the tools, reflects on the evidence, and synthesizes the dossier.</p>
        </header>
        <div className="legend-grid">
          {[
            { name: "Plan", rule: "Extract ticker · decompose query", icon: "1" },
            { name: "Tools", rule: "Market · news · correlation", icon: "2" },
            { name: "Reflect", rule: "Critique · re-plan if needed", icon: "3" },
          ].map((t) => (
            <div key={t.name}>
              <div className="icon">{t.icon}</div>
              <div className="name">{t.name}</div>
              <div className="rule">{t.rule}</div>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
