export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export async function postAnalyze(query: string): Promise<{ job_id: string }> {
  const r = await fetch(`${API_BASE}/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
  if (!r.ok) throw new Error(`POST /analyze failed: ${r.status}`);
  return r.json();
}

export async function getStatus(jobId: string): Promise<any> {
  const r = await fetch(`${API_BASE}/status/${jobId}`);
  if (!r.ok) throw new Error(`status ${r.status}`);
  return r.json();
}

export async function postMonitorStart(
  ticker: string,
  cadence_seconds = 86400,
  peers: string[] = [],
): Promise<any> {
  const r = await fetch(`${API_BASE}/monitor_start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ticker, cadence_seconds, peers }),
  });
  if (!r.ok) {
    // Surface the structured 400 body so the UI can show "TSLA: NO_HISTORY"
    // instead of a generic "monitor_start 400". Backend returns
    // {detail: {code, ticker, reason}} on BASELINE_COMPUTE_FAILED.
    const body = await r.json().catch(() => null);
    const detail = body?.detail;
    if (detail?.code === "BASELINE_COMPUTE_FAILED") {
      throw new Error(`BASELINE_COMPUTE_FAILED:${detail.ticker}:${detail.reason || "unknown"}`);
    }
    throw new Error(`monitor_start ${r.status}`);
  }
  return r.json();
}

export async function listMonitors(): Promise<any[]> {
  const r = await fetch(`${API_BASE}/monitor`);
  return r.ok ? r.json() : [];
}

export async function deleteMonitor(ticker: string): Promise<void> {
  const r = await fetch(`${API_BASE}/monitor/${ticker}`, { method: "DELETE" });
  // Backend is idempotent (returns 200 even on missing rows). Tolerate
  // 404 from older builds for safety; throw on real failures so the UI
  // can surface a toast rather than silently no-op'ing.
  if (!r.ok && r.status !== 404) {
    throw new Error(`delete_monitor ${r.status}`);
  }
}

export type ResolvedItem = {
  input: string;
  status: "ok" | "corrected" | "invalid";
  ticker?: string | null;
  company_name?: string | null;
  message?: string | null;
};

export async function resolveTickers(inputs: string[]): Promise<ResolvedItem[]> {
  const r = await fetch(`${API_BASE}/resolve_tickers`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ inputs }),
  });
  if (!r.ok) throw new Error(`resolve_tickers ${r.status}`);
  const body = await r.json();
  return body.results || [];
}

export async function monitorHistory(ticker: string): Promise<any[]> {
  const r = await fetch(`${API_BASE}/monitor/${ticker}/history`);
  return r.ok ? r.json() : [];
}
