"use client";

import { useJobStream } from "@/lib/sse";

const KIND_FOR: Record<string, string> = {
  ticker_resolved: "plan",
  ticker_resolution_failed: "error",
  planner_decision: "plan",
  tool_start: "tool",
  tool_end: "tool",
  reflection_thought: "reflect",
  replan: "reflect",
  synthesis_token: "synth",
  done: "done",
  error: "error",
};

function describe(ev: { event: string; data: any }) {
  const { event, data } = ev;
  if (event === "ticker_resolved") return `resolved ticker → ${data?.ticker || "?"}`;
  if (event === "ticker_resolution_failed") return `ticker resolution failed: ${data?.reason || "unknown"}`;
  if (event === "planner_decision") return `plan · next=${data?.next_node || data?.decision || "?"}`;
  if (event === "tool_start") return `tool ${data?.name || "?"} → ${JSON.stringify(data?.input || {})}`;
  if (event === "tool_end") return `tool ${data?.name || "?"} ✓ ${data?.latency_ms ?? "?"}ms`;
  if (event === "reflection_thought") return `reflect · ${data?.thought || "..."}`;
  if (event === "replan") return `replan · ${data?.reason || "triggers fired"}`;
  if (event === "synthesis_token") return null; // skip in feed (too noisy)
  if (event === "done") return "done";
  if (event === "error") return `error · ${data?.message || data?.error || "unknown"}`;
  if (event === "ping") return null;
  return event;
}

export default function ProcessingScreen({ jobId, query }: { jobId: string; query?: string }) {
  const { events } = useJobStream(jobId);
  const displayed = events.filter((e) => describe(e) != null);

  return (
    <main className="container">
      <section className="hero">
        <div className="h-row">
          <span className="badge">Job {jobId.slice(0, 8)}</span>
          <span>analysis in progress</span>
        </div>
        <h1 className="headline">Working on it…</h1>
        <p className="subhead">
          MIRA is planning, calling tools, reflecting, and synthesizing. Live agent events stream below.
        </p>
        {query && (
          <p className="mono" style={{ marginTop: 18, color: "var(--muted)", fontSize: 13 }}>
            &gt; {query}
          </p>
        )}
      </section>

      <div className="card" style={{ padding: 24, marginTop: 12 }}>
        <div className="eyebrow" style={{ marginBottom: 14 }}>Live agent stream</div>
        {displayed.length === 0 ? (
          <div className="mono" style={{ color: "var(--muted)", fontSize: 12 }}>
            connecting to /status/{jobId}/stream …
          </div>
        ) : (
          <div className="proc-events">
            {displayed.slice(-200).map((e, i) => {
              const kind = KIND_FOR[e.event] || "plan";
              return (
                <div className="proc-event" key={i}>
                  <span className="ts">{new Date().toLocaleTimeString()}</span>
                  <span className={"kind " + kind}>{kind}</span>
                  <span className="body">{describe(e)}</span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </main>
  );
}
