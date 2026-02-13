"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
} from "@/components/ui/card";
import {
  Radar,
  Loader2,
  Square,
  Globe,
  FileText,
  Database,
  AlertCircle,
  CheckCircle2,
  XCircle,
  Timer,
  Clock,
  Sparkles,
  ExternalLink,
  Search,
  BookOpen,
  ArrowDownToLine,
} from "lucide-react";
import {
  startMonitor,
  getMonitorStatus,
  getMonitorJobs,
  stopMonitor,
  getMonitorQueries,
  type MonitorQuery,
  type MonitorJob,
  type MonitorNewUrl,
} from "@/lib/api";
import { useProject } from "@/lib/project-context";

const RECENCY_OPTIONS = [
  { value: "week", label: "Past Week" },
  { value: "month", label: "Past Month" },
  { value: "year", label: "Past Year" },
];

const STAT_CARDS = [
  {
    key: "urls_found",
    label: "URLs Found",
    icon: Globe,
    color: "text-indigo-600",
    bg: "bg-indigo-50",
    border: "border-indigo-100",
  },
  {
    key: "existing_urls",
    label: "Already Indexed",
    icon: Database,
    color: "text-slate-600",
    bg: "bg-slate-50",
    border: "border-slate-100",
  },
  {
    key: "new_urls",
    label: "New Content",
    icon: Sparkles,
    color: "text-emerald-600",
    bg: "bg-emerald-50",
    border: "border-emerald-100",
  },
  {
    key: "ingested",
    label: "Ingested",
    icon: ArrowDownToLine,
    color: "text-blue-600",
    bg: "bg-blue-50",
    border: "border-blue-100",
  },
];

function formatElapsed(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  if (mins === 0) return `${secs}s`;
  return `${mins}m ${secs}s`;
}

function StepNumber({ n, active }: { n: number; active: boolean }) {
  return (
    <span
      className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold transition-colors ${
        active
          ? "bg-primary text-primary-foreground"
          : "bg-muted text-muted-foreground"
      }`}
    >
      {n}
    </span>
  );
}

function statusBadge(status: string) {
  switch (status) {
    case "ingested":
      return <Badge className="bg-emerald-100 text-emerald-700 border-emerald-200">Ingested</Badge>;
    case "failed":
    case "db_error":
      return <Badge variant="destructive">Failed</Badge>;
    case "skipped":
      return <Badge variant="secondary">Skipped</Badge>;
    default:
      return <Badge variant="outline" className="text-blue-600 border-blue-200">New</Badge>;
  }
}

function categoryColor(category: string): string {
  if (category.includes("WAC")) return "bg-violet-500";
  if (category.includes("ETA")) return "bg-amber-500";
  if (category.includes("WTD")) return "bg-blue-500";
  if (category.includes("Publication")) return "bg-emerald-500";
  if (category.includes("Industry")) return "bg-cyan-500";
  if (category.includes("Rate")) return "bg-orange-500";
  return "bg-slate-500";
}

export default function MonitorPage() {
  const { activeProject } = useProject();
  const [recency, setRecency] = useState("month");
  const [autoIngest, setAutoIngest] = useState(false);
  const [generateSummary, setGenerateSummary] = useState(true);
  const [queries, setQueries] = useState<MonitorQuery[]>([]);

  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [activeJob, setActiveJob] = useState<MonitorJob | null>(null);
  const [jobs, setJobs] = useState<MonitorJob[]>([]);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Load queries and past jobs on mount
  useEffect(() => {
    getMonitorQueries().then(setQueries).catch(() => {});
    getMonitorJobs().then(setJobs).catch(() => {});
  }, []);

  // Poll active job status
  useEffect(() => {
    if (!activeJobId) return;

    const poll = async () => {
      try {
        const status = await getMonitorStatus(activeJobId);
        setActiveJob(status);
        if (
          status.status === "complete" ||
          status.status === "stopped" ||
          status.status === "error"
        ) {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
          getMonitorJobs().then(setJobs).catch(() => {});
        }
      } catch {
        /* ignore */
      }
    };

    poll();
    pollRef.current = setInterval(poll, 2000);

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [activeJobId]);

  async function handleStart() {
    try {
      const { job_id } = await startMonitor(
        activeProject?.id,
        recency,
        autoIngest,
        generateSummary,
      );
      setActiveJobId(job_id);
      setActiveJob(null);
    } catch (err) {
      console.error(err);
    }
  }

  async function handleStop() {
    if (activeJobId) {
      await stopMonitor(activeJobId);
    }
  }

  const isRunning =
    activeJob?.status === "running" || activeJob?.status === "starting";
  const isComplete = activeJob?.status === "complete";
  const progressPct =
    activeJob && activeJob.total_queries > 0
      ? Math.min(100, (activeJob.queries_completed / activeJob.total_queries) * 100)
      : 0;

  const pastJobs = jobs.filter((j) => j.job_id !== activeJobId).slice(0, 10);
  const hasResults = activeJob && (isComplete || activeJob.status === "stopped");

  return (
    <div className="max-w-4xl space-y-8">
      {/* Hero section */}
      <div>
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/10 mb-3">
          <Radar className="h-6 w-6 text-primary" />
        </div>
        <h2 className="text-2xl font-bold tracking-tight">Monitor</h2>
        <p className="text-muted-foreground mt-1">
          Use Perplexity AI to detect new or updated content on dor.wa.gov and
          automatically update your knowledge base.
        </p>
      </div>

      {/* Step 1: Configure */}
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <StepNumber n={1} active={!activeJob} />
          <div>
            <p className="text-sm font-semibold">Configure</p>
            <p className="text-xs text-muted-foreground">
              Set search parameters and options
            </p>
          </div>
        </div>

        <Card className="ml-10">
          <CardContent className="p-5 space-y-4">
            {/* Recency filter */}
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1.5 block">
                Search recency
              </label>
              <div className="flex gap-2">
                {RECENCY_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    onClick={() => setRecency(opt.value)}
                    disabled={isRunning}
                    className={`px-3 py-1.5 rounded-full text-sm border transition-colors ${
                      recency === opt.value
                        ? "bg-primary text-primary-foreground border-primary"
                        : "bg-background border-border text-muted-foreground hover:border-primary/30 hover:bg-accent"
                    }`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Toggles */}
            <div className="flex flex-wrap gap-4">
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input
                  type="checkbox"
                  checked={autoIngest}
                  onChange={(e) => setAutoIngest(e.target.checked)}
                  disabled={isRunning}
                  className="rounded"
                />
                <span className={autoIngest ? "text-foreground" : "text-muted-foreground"}>
                  Auto-ingest new content
                </span>
              </label>
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input
                  type="checkbox"
                  checked={generateSummary}
                  onChange={(e) => setGenerateSummary(e.target.checked)}
                  disabled={isRunning}
                  className="rounded"
                />
                <span className={generateSummary ? "text-foreground" : "text-muted-foreground"}>
                  Generate AI summary
                </span>
              </label>
            </div>

            {/* Search queries preview */}
            {queries.length > 0 && (
              <div>
                <label className="text-xs font-medium text-muted-foreground mb-1.5 block">
                  Searches to run ({queries.length})
                </label>
                <div className="flex flex-wrap gap-1.5">
                  {queries.map((q) => (
                    <Badge key={q.id} variant="secondary" className="gap-1 text-xs">
                      <Search className="h-2.5 w-2.5" />
                      {q.label}
                    </Badge>
                  ))}
                </div>
              </div>
            )}

            {/* Action buttons */}
            <div className="flex gap-2 pt-1">
              <Button
                onClick={handleStart}
                disabled={isRunning}
                className="gap-2"
              >
                {isRunning ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Radar className="h-4 w-4" />
                )}
                {isRunning ? "Scanning..." : "Run Check"}
              </Button>
              {isRunning && (
                <Button variant="destructive" onClick={handleStop} className="gap-2">
                  <Square className="h-3.5 w-3.5" />
                  Stop
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Step 2: Scanning Progress */}
      {activeJob && (
        <div className="space-y-4">
          <div className="flex items-center gap-3">
            <StepNumber n={2} active={isRunning} />
            <div>
              <p className="text-sm font-semibold">
                {isRunning ? "Scanning" : isComplete ? "Scan Complete" : `Scan ${activeJob.status === "error" ? "Failed" : "Stopped"}`}
              </p>
              <p className="text-xs text-muted-foreground">
                Job {activeJob.job_id} &middot;{" "}
                {formatElapsed(activeJob.elapsed_seconds)}
              </p>
            </div>
          </div>

          <div className="ml-10 space-y-4">
            {/* Progress bar */}
            <div>
              <div className="flex justify-between text-xs text-muted-foreground mb-1.5">
                <span>
                  {activeJob.queries_completed} / {activeJob.total_queries} queries
                </span>
                <span className="font-medium">{Math.round(progressPct)}%</span>
              </div>
              <div className="w-full bg-muted rounded-full h-2.5 overflow-hidden">
                <div
                  className={`h-2.5 rounded-full transition-all duration-500 ${
                    isRunning
                      ? "bg-gradient-to-r from-primary via-primary/80 to-primary animate-pulse"
                      : isComplete
                        ? "bg-emerald-500"
                        : activeJob.status === "error"
                          ? "bg-red-500"
                          : "bg-yellow-500"
                  }`}
                  style={{ width: `${progressPct}%` }}
                />
              </div>
            </div>

            {/* Current query */}
            {isRunning && activeJob.current_query && (
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-primary" />
                </span>
                <span className="truncate">{activeJob.current_query}</span>
              </div>
            )}

            {/* Stat cards */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {STAT_CARDS.map(({ key, label, icon: Icon, color, bg, border }) => (
                <Card
                  key={key}
                  className={`border ${border} transition-shadow hover:shadow-sm`}
                >
                  <CardContent className="p-4">
                    <div className="flex items-start justify-between">
                      <div>
                        <p className="text-xs text-muted-foreground">{label}</p>
                        <p className="text-2xl font-bold tracking-tight mt-1">
                          {(
                            (activeJob as unknown as Record<string, number>)[key]
                          )?.toLocaleString() ?? 0}
                        </p>
                      </div>
                      <div
                        className={`flex h-8 w-8 items-center justify-center rounded-lg ${bg}`}
                      >
                        <Icon className={`h-4 w-4 ${color}`} />
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Step 3: Results */}
      {hasResults && (
        <div className="space-y-4">
          <div className="flex items-center gap-3">
            <StepNumber n={3} active={true} />
            <div>
              <p className="text-sm font-semibold">Results</p>
              <p className="text-xs text-muted-foreground">
                {activeJob!.new_urls} new page{activeJob!.new_urls !== 1 ? "s" : ""} found
                {activeJob!.ingested > 0 && `, ${activeJob!.ingested} ingested`}
              </p>
            </div>
          </div>

          <div className="ml-10 space-y-4">
            {/* AI Summary */}
            {activeJob!.summary && (
              <Card className="border-primary/20 bg-primary/5">
                <CardContent className="p-5">
                  <div className="flex items-center gap-2 mb-3">
                    <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/10">
                      <Sparkles className="h-3.5 w-3.5 text-primary" />
                    </div>
                    <span className="text-sm font-semibold">AI Summary</span>
                  </div>
                  <p className="text-sm text-muted-foreground leading-relaxed whitespace-pre-wrap">
                    {activeJob!.summary}
                  </p>
                </CardContent>
              </Card>
            )}

            {/* New URLs list */}
            {activeJob!.new_url_list.length > 0 ? (
              <div>
                <p className="text-xs font-medium text-muted-foreground mb-2">
                  New pages discovered
                </p>
                <div className="space-y-2">
                  {activeJob!.new_url_list.map((item: MonitorNewUrl, i: number) => (
                    <div
                      key={i}
                      className="rounded-lg border p-3.5 hover:bg-muted/50 transition-colors"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2 mb-1">
                            <a
                              href={item.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-sm font-medium hover:text-primary transition-colors truncate"
                            >
                              {item.title || item.url}
                              <ExternalLink className="inline h-3 w-3 ml-1 opacity-50" />
                            </a>
                          </div>
                          <div className="flex items-center gap-2 mb-1.5">
                            <Badge variant="secondary" className="gap-1 text-xs pl-1.5">
                              <span className={`h-1.5 w-1.5 rounded-full ${categoryColor(item.category)}`} />
                              {item.category}
                            </Badge>
                            {statusBadge(item.status)}
                            {item.date && (
                              <span className="text-xs text-muted-foreground">
                                {item.date}
                              </span>
                            )}
                          </div>
                          {item.snippet && (
                            <p className="text-xs text-muted-foreground line-clamp-2">
                              {item.snippet}
                            </p>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-8 text-center">
                <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-50 mb-3">
                  <CheckCircle2 className="h-6 w-6 text-emerald-500" />
                </div>
                <p className="text-sm font-medium">Knowledge base is up to date</p>
                <p className="text-xs text-muted-foreground mt-1">
                  No new content was found on dor.wa.gov
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Empty state */}
      {!activeJob && pastJobs.length === 0 && (
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-muted mb-4">
            <Radar className="h-7 w-7 text-muted-foreground" />
          </div>
          <p className="text-sm font-medium">No monitor activity yet</p>
          <p className="text-xs text-muted-foreground mt-1 max-w-sm">
            Click &quot;Run Check&quot; to scan dor.wa.gov for new content using
            Perplexity AI search.
          </p>
        </div>
      )}

      {/* Job History */}
      {pastJobs.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <Clock className="h-4 w-4 text-muted-foreground" />
            <h3 className="text-sm font-medium">Check History</h3>
          </div>
          <div className="space-y-2">
            {pastJobs.map((job) => (
              <div
                key={job.job_id}
                className="flex items-center justify-between rounded-lg border p-3.5 hover:bg-muted/50 transition-colors"
              >
                <div className="flex items-center gap-3 min-w-0">
                  {job.status === "complete" ? (
                    <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" />
                  ) : job.status === "error" ? (
                    <XCircle className="h-4 w-4 text-red-500 shrink-0" />
                  ) : (
                    <Timer className="h-4 w-4 text-yellow-500 shrink-0" />
                  )}
                  <div className="min-w-0">
                    <p className="text-sm font-medium">
                      {job.new_urls} new &middot; {job.urls_found} total found
                      {job.ingested > 0 && ` &middot; ${job.ingested} ingested`}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {formatElapsed(job.elapsed_seconds)}
                    </p>
                  </div>
                </div>
                <code className="text-xs text-muted-foreground shrink-0 ml-4">
                  {job.job_id}
                </code>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
