"use client";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { getStatus } from "@/lib/api";
import { useJobStream } from "@/lib/sse";

export default function JobPage() {
  const params = useParams<{ id: string }>();
  const jobId = params.id;
  const { events, done } = useJobStream(jobId);
  const [status, setStatus] = useState<any>(null);

  useEffect(() => {
    if (!jobId) return;
    let stop = false;
    const tick = async () => {
      try { setStatus(await getStatus(jobId)); } catch {}
      if (!stop && !done) setTimeout(tick, 2000);
    };
    tick();
    return () => { stop = true; };
  }, [jobId, done]);

  const tokens = useMemo(() => events.filter(e => e.event === "synthesis_token").map(e => e.data?.token || "").join(""), [events]);
  const report = status?.report;

  return (
    <div className="grid lg:grid-cols-2 gap-6">
      <div>
        <h2 className="text-xl font-semibold mb-3">Agent live stream</h2>
        <div className="border rounded-lg bg-gray-50 p-3 max-h-[70vh] overflow-y-auto text-sm font-mono space-y-1">
          {events.length === 0 && <div className="text-gray-400">Waiting for events…</div>}
          {events.map((e, i) => (
            <EventLine key={i} ev={e} />
          ))}
          {tokens && (
            <div className="mt-3 p-2 rounded border bg-white">
              <div className="text-[10px] uppercase tracking-wider text-gray-400 mb-1">Synthesis (live)</div>
              <pre className="whitespace-pre-wrap text-xs">{tokens.slice(0, 4000)}</pre>
            </div>
          )}
        </div>
      </div>

      <div>
        <h2 className="text-xl font-semibold mb-3">Report</h2>
        <div className="border rounded-lg p-4 space-y-4">
          <div className="text-sm text-gray-500">Status: <b>{status?.status || "loading…"}</b></div>
          {report ? <Report r={report} /> : (
            <div className="text-gray-400 text-sm">
              {status?.status === "failed" ? `Failed: ${status?.error}` : "Awaiting completion…"}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function EventLine({ ev }: { ev: { event: string; data: any } }) {
  const color: Record<string, string> = {
    planner_decision: "text-blue-600",
    tool_start: "text-purple-600",
    tool_end: "text-purple-700",
    reflection_thought: "text-amber-600",
    replan: "text-amber-700 font-semibold",
    ticker_resolved: "text-emerald-600",
    done: "text-emerald-700 font-semibold",
    error: "text-red-600",
  };
  if (ev.event === "synthesis_token" || ev.event === "ping") return null;
  return (
    <div className={color[ev.event] || ""}>
      <span className="text-[10px] uppercase tracking-wider mr-2">{ev.event}</span>
      <span>{summarize(ev.data)}</span>
    </div>
  );
}

function summarize(d: any): string {
  if (!d) return "";
  if (typeof d === "string") return d;
  if (d.plan) return `${d.plan}  [${(d.tools || []).join(", ")}]`;
  if (d.tool) return `${d.tool}${d.output_summary ? ` → ${d.output_summary}` : ""}`;
  if (d.trigger_evaluated) return `${d.trigger_evaluated}: ${d.fired ? "FIRED" : "skip"} — ${d.reasoning}`;
  if (d.triggers_fired) return `triggers: ${d.triggers_fired.join(", ")} (pass ${d.pass})`;
  if (d.message) return d.message;
  if (d.report) return "report ready";
  return JSON.stringify(d).slice(0, 200);
}

function Report({ r }: { r: any }) {
  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-2xl font-bold">{r.company_name} <span className="text-gray-400">({r.company_ticker})</span></h3>
        <div className="text-sm text-gray-500">Sentiment {Number(r.sentiment_score).toFixed(2)} · Confidence {Number(r.confidence ?? 1).toFixed(2)} {r.degraded ? <span className="ml-2 text-amber-700">DEGRADED ({r.degradation_reason})</span> : null}</div>
      </div>

      <section>
        <h4 className="font-semibold mb-1">Summary</h4>
        <p className="text-sm">{r.analysis_summary}</p>
      </section>

      <section>
        <h4 className="font-semibold mb-1">Key findings</h4>
        <ol className="list-decimal list-inside text-sm space-y-1">
          {(r.key_findings || []).map((f: string, i: number) => <li key={i}>{f}</li>)}
        </ol>
      </section>

      <section>
        <h4 className="font-semibold mb-1">Market snapshot</h4>
        <pre className="text-xs bg-gray-50 p-2 rounded overflow-x-auto">{JSON.stringify(r.market_snapshot, null, 2)}</pre>
      </section>

      <section>
        <h4 className="font-semibold mb-1">Correlations</h4>
        <pre className="text-xs bg-gray-50 p-2 rounded overflow-x-auto">{JSON.stringify(r.correlation_analysis, null, 2)}</pre>
      </section>

      <section>
        <h4 className="font-semibold mb-1">Citations</h4>
        <ul className="text-xs space-y-1">
          {(r.citation_sources || []).map((u: string, i: number) => (
            <li key={i}><a href={u} target="_blank" rel="noreferrer" className="text-blue-600 underline">{u}</a></li>
          ))}
        </ul>
      </section>

      <section className="text-xs text-gray-500">
        Tools used (in order): {(r.tools_used || []).join(" → ")} · Reflection passes: {r.reflection_passes}
        {r.triggers_fired?.length ? <> · Triggers fired: {r.triggers_fired.join(", ")}</> : null}
        <div>Cost: ${Number(r.token_usage?.cost_usd ?? 0).toFixed(6)} · Tokens: {r.token_usage?.total_tokens}</div>
      </section>
    </div>
  );
}
