"use client";

import { useEffect, useState } from "react";
import { getStatus } from "@/lib/api";
import ReportView, { type Report } from "@/components/mira/Report";
import ProcessingScreen from "@/components/mira/Processing";

interface JobStatus {
  job_id: string;
  query: string;
  status: "queued" | "running" | "completed" | "failed";
  report?: Report;
  error?: string;
}

export default function JobPage({ params }: { params: { id: string } }) {
  const jobId = params.id;
  const [job, setJob] = useState<JobStatus | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | null = null;

    async function poll() {
      try {
        const data = (await getStatus(jobId)) as JobStatus;
        if (!alive) return;
        setJob(data);
        if (typeof window !== "undefined") {
          window.localStorage.setItem("mira:last-job-id", jobId);
        }
        if (data.status === "completed" || data.status === "failed") return;
      } catch (e: unknown) {
        if (!alive) return;
        const msg = e instanceof Error ? e.message : "status fetch failed";
        setErr(msg);
        if (typeof window !== "undefined" && msg.includes("404")) {
          const stored = window.localStorage.getItem("mira:last-job-id");
          if (stored === jobId) {
            window.localStorage.removeItem("mira:last-job-id");
          }
        }
      }
      timer = setTimeout(poll, 2000);
    }
    poll();
    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
    };
  }, [jobId]);

  if (err && !job) {
    return (
      <main className="container">
        <section className="hero">
          <div className="h-row">
            <span className="badge" style={{ color: "var(--neg)", borderColor: "var(--neg)" }}>error</span>
          </div>
          <h1 className="headline">Couldn&apos;t load job.</h1>
          <p className="subhead mono">{err}</p>
        </section>
      </main>
    );
  }

  if (!job) {
    return (
      <main className="container">
        <section className="hero">
          <h1 className="headline">Loading…</h1>
          <p className="subhead mono">job {jobId.slice(0, 8)}</p>
        </section>
      </main>
    );
  }

  if (job.status === "failed") {
    return (
      <main className="container">
        <section className="hero">
          <div className="h-row">
            <span className="badge" style={{ color: "var(--neg)", borderColor: "var(--neg)" }}>job failed</span>
          </div>
          <h1 className="headline">Analysis failed.</h1>
          <p className="subhead mono">{job.error || "unknown error"}</p>
        </section>
      </main>
    );
  }

  if (job.status !== "completed" || !job.report) {
    return <ProcessingScreen jobId={jobId} query={job.query} />;
  }

  return <ReportView report={job.report} jobId={jobId} />;
}
