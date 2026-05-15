"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { postAnalyze } from "@/lib/api";

const SAMPLES = [
  "Analyze the near-term prospects of Tesla, Inc. (TSLA).",
  "What's the outlook for Apple (AAPL) given recent news?",
  "Should I be concerned about Coca-Cola (KO) right now?",
  "Deep dive on NVDA fundamentals and sentiment.",
];

export default function SubmitPage() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(q: string) {
    setErr(null);
    setLoading(true);
    try {
      const { job_id } = await postAnalyze(q);
      router.push(`/jobs/${job_id}`);
    } catch (e: any) {
      setErr(e.message || "Failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold mb-2">Submit an analysis</h1>
        <p className="text-gray-600">
          M.I.R.A. plans research, calls tools (market data, news, correlations, SEC filings),
          reflects on the evidence, and produces a structured investment analysis.
        </p>
      </div>

      <form
        onSubmit={(e) => { e.preventDefault(); if (query.trim()) submit(query.trim()); }}
        className="space-y-4"
      >
        <textarea
          className="w-full border rounded-lg p-4 min-h-[120px] focus:outline-none focus:ring-2 focus:ring-accent"
          placeholder='e.g. "Analyze the near-term prospects of Tesla, Inc. (TSLA)."'
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <div className="flex items-center justify-between">
          <button
            type="submit"
            disabled={loading || !query.trim()}
            className="bg-accent text-white px-6 py-2 rounded-lg font-semibold hover:bg-accent-600 disabled:opacity-50"
          >
            {loading ? "Submitting…" : "Analyze"}
          </button>
          {err && <span className="text-red-600 text-sm">{err}</span>}
        </div>
      </form>

      <div>
        <h2 className="text-sm font-semibold text-gray-500 uppercase mb-2">Try a sample</h2>
        <div className="grid sm:grid-cols-2 gap-2">
          {SAMPLES.map((s) => (
            <button
              key={s}
              onClick={() => submit(s)}
              className="text-left border rounded-lg p-3 hover:border-accent hover:bg-accent-50"
            >
              {s}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
