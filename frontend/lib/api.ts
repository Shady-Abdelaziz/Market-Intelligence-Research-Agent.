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
  if (!r.ok) throw new Error(`monitor_start ${r.status}`);
  return r.json();
}

export async function listMonitors(): Promise<any[]> {
  const r = await fetch(`${API_BASE}/monitor`);
  return r.ok ? r.json() : [];
}

export async function deleteMonitor(ticker: string): Promise<void> {
  await fetch(`${API_BASE}/monitor/${ticker}`, { method: "DELETE" });
}

export async function monitorHistory(ticker: string): Promise<any[]> {
  const r = await fetch(`${API_BASE}/monitor/${ticker}/history`);
  return r.ok ? r.json() : [];
}
