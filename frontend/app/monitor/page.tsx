"use client";
import { useEffect, useState } from "react";
import { deleteMonitor, listMonitors, monitorHistory, postMonitorStart } from "@/lib/api";

export default function MonitorPage() {
  const [monitors, setMonitors] = useState<any[]>([]);
  const [ticker, setTicker] = useState("");
  const [cadence, setCadence] = useState(86400);
  const [peers, setPeers] = useState("");
  const [history, setHistory] = useState<Record<string, any[]>>({});
  const [err, setErr] = useState<string | null>(null);

  async function refresh() {
    setMonitors(await listMonitors());
  }
  useEffect(() => { refresh(); }, []);

  async function add() {
    setErr(null);
    try {
      await postMonitorStart(ticker.toUpperCase(), cadence, peers.split(",").map(s => s.trim()).filter(Boolean));
      setTicker("");
      setPeers("");
      await refresh();
    } catch (e: any) {
      setErr(e.message || "failed");
    }
  }

  async function remove(t: string) {
    await deleteMonitor(t);
    await refresh();
  }

  async function loadHistory(t: string) {
    setHistory((h) => ({ ...h, [t]: [] }));
    const rows = await monitorHistory(t);
    setHistory((h) => ({ ...h, [t]: rows }));
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Persistent monitors</h1>
        <p className="text-gray-600 mt-1">
          M.I.R.A. wakes on a cadence (default 24h, trading days only) and reruns analysis when
          ≥5 new articles, a 2σ price move, or 2× volume spike fires.
        </p>
      </div>

      <div className="border rounded-lg p-4 space-y-3">
        <h2 className="font-semibold">Add monitor</h2>
        <div className="flex gap-2 flex-wrap items-end">
          <label className="flex flex-col text-sm">Ticker
            <input value={ticker} onChange={e => setTicker(e.target.value)} className="border rounded px-2 py-1 w-32" />
          </label>
          <label className="flex flex-col text-sm">Cadence (s)
            <input type="number" value={cadence} onChange={e => setCadence(parseInt(e.target.value) || 0)} className="border rounded px-2 py-1 w-32" />
          </label>
          <label className="flex flex-col text-sm flex-1">Peers (comma)
            <input value={peers} onChange={e => setPeers(e.target.value)} className="border rounded px-2 py-1" placeholder="MSFT, GOOGL" />
          </label>
          <button onClick={add} className="bg-accent text-white px-4 py-2 rounded font-semibold">Start</button>
        </div>
        {err && <div className="text-red-600 text-sm">{err}</div>}
      </div>

      <div className="space-y-3">
        {monitors.length === 0 && <div className="text-gray-400">No active monitors.</div>}
        {monitors.map((m) => (
          <div key={m.ticker} className="border rounded-lg p-4">
            <div className="flex justify-between items-center">
              <div>
                <div className="font-semibold text-lg">{m.ticker}</div>
                <div className="text-xs text-gray-500">
                  cadence {m.cadence_seconds}s · last_run {m.last_run_at || "—"} ·
                  baseline price {m.baseline_price_mean ? m.baseline_price_mean.toFixed(2) : "—"} ± {m.baseline_price_std?.toFixed(2) || "—"}
                </div>
              </div>
              <div className="flex gap-2">
                <button onClick={() => loadHistory(m.ticker)} className="text-sm border rounded px-3 py-1">History</button>
                <button onClick={() => remove(m.ticker)} className="text-sm border rounded px-3 py-1 text-red-600">Stop</button>
              </div>
            </div>
            {history[m.ticker] && (
              <div className="mt-3 border-t pt-3 text-xs">
                {history[m.ticker].length === 0 && <div className="text-gray-400">No proactive alerts yet.</div>}
                {history[m.ticker].map((h: any) => (
                  <div key={h.job_id} className="py-1">
                    <a href={`/jobs/${h.job_id}`} className="text-blue-600 underline">{h.created_at}</a>
                    {" — "}
                    <span>{(h.triggers_fired || []).join(", ")}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
