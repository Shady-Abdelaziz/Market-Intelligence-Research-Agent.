"use client";
import { useEffect, useRef, useState } from "react";
import { API_BASE } from "./api";

export type SSEEvent = { event: string; data: any; id?: string };

export function useJobStream(jobId: string | null) {
  const [events, setEvents] = useState<SSEEvent[]>([]);
  const [done, setDone] = useState(false);
  const ref = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!jobId) return;
    setEvents([]);
    setDone(false);
    const es = new EventSource(`${API_BASE}/status/${jobId}/stream`);
    ref.current = es;

    const types = [
      "ticker_resolved", "ticker_resolution_failed", "planner_decision",
      "tool_start", "tool_end", "reflection_thought", "replan",
      "synthesis_token", "done", "error", "ping",
    ];

    const onAny = (type: string) => (e: MessageEvent) => {
      let data: any = e.data;
      try { data = JSON.parse(e.data); } catch {}
      setEvents((prev) => [...prev, { event: type, data, id: (e as any).lastEventId }]);
      if (type === "done" || type === "error") {
        setDone(true);
        es.close();
      }
    };

    types.forEach((t) => es.addEventListener(t, onAny(t) as any));
    es.onerror = () => { /* let it reconnect */ };
    return () => { es.close(); ref.current = null; };
  }, [jobId]);

  return { events, done };
}
