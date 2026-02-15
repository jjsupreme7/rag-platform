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
  ArrowDownToLine,
  RefreshCw,
  Eye,
  AlertTriangle,
  Plus,
  Trash2,
} from "lucide-react";
import {
  startMonitor,
  getMonitorStatus,
  getMonitorJobs,
  stopMonitor,
  getMonitorQueries,
  startCrawl,
  getCrawlStatus,
  getCrawlJobs,
  stopCrawl,
  getMonitoredPages,
  getMonitorChanges,
  addMonitoredPage,
  removeMonitoredPage,
  getSchedule,
  updateSchedule,
  approveChange,
  dismissChange,
  type MonitorQuery,
  type MonitorJob,
  type MonitorNewUrl,
  type CrawlJob,
  type MonitoredPage,
  type ChangeLogEntry,
  type ScheduleConfig,
} from "@/lib/api";
import { useProject } from "@/lib/project-context";

function formatElapsed(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  if (mins === 0) return `${secs}s`;
  return `${mins}m ${secs}s`;
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return "Never";
  const d = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffHrs = diffMs / (1000 * 60 * 60);
  if (diffHrs < 1) return `${Math.round(diffMs / 60000)}m ago`;
  if (diffHrs < 24) return `${Math.round(diffHrs)}h ago`;
  const diffDays = Math.round(diffHrs / 24);
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7) return `${diffDays}d ago`;
  return d.toLocaleDateString();
}

function changeTypeBadge(type: string) {
  switch (type) {
    case "NEW":
      return <Badge className="bg-emerald-100 text-emerald-700 border-emerald-200">New</Badge>;
    case "MODIFIED":
      return <Badge className="bg-amber-100 text-amber-700 border-amber-200">Modified</Badge>;
    case "REMOVED":
      return <Badge variant="destructive">Removed</Badge>;
    default:
      return <Badge variant="outline">{type}</Badge>;
  }
}

function statusDot(status: string) {
  if (status === "active") return "bg-emerald-500";
  if (status === "error") return "bg-red-500";
  return "bg-slate-400";
}

// ==========================================================================
// Page Monitor Tab
// ==========================================================================

function PageMonitorTab() {
  const { activeProject } = useProject();
  const [autoIngest, setAutoIngest] = useState(true);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [activeJob, setActiveJob] = useState<CrawlJob | null>(null);
  const [pages, setPages] = useState<MonitoredPage[]>([]);
  const [changes, setChanges] = useState<ChangeLogEntry[]>([]);
  const [showPages, setShowPages] = useState(false);
  const [newUrl, setNewUrl] = useState("");
  const [loadingPages, setLoadingPages] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Schedule state
  const [schedule, setSchedule] = useState<ScheduleConfig | null>(null);
  const [scheduleLoading, setScheduleLoading] = useState(false);

  // Load pages, changes, and schedule on mount
  useEffect(() => {
    loadPages();
    loadChanges();
    loadSchedule();
    // Check for running crawl jobs
    getCrawlJobs().then((jobs) => {
      const running = jobs.find((j) => j.status === "running" || j.status === "starting");
      if (running) {
        setActiveJobId(running.job_id);
      }
    }).catch(() => {});
  }, [activeProject?.id]);

  function loadPages() {
    setLoadingPages(true);
    getMonitoredPages(activeProject?.id)
      .then((data) => setPages(data.pages))
      .catch(() => {})
      .finally(() => setLoadingPages(false));
  }

  function loadChanges() {
    getMonitorChanges(activeProject?.id, 20, 0, undefined, true)
      .then((data) => setChanges(data.changes))
      .catch(() => {});
  }

  function loadSchedule() {
    getSchedule()
      .then(setSchedule)
      .catch(() => {});
  }

  async function handleScheduleToggle(enabled: boolean) {
    setScheduleLoading(true);
    try {
      const updated = await updateSchedule({ enabled });
      setSchedule(updated);
    } catch (err) {
      console.error(err);
    } finally {
      setScheduleLoading(false);
    }
  }

  async function handleScheduleTimeChange(hour: number, minute: number) {
    setScheduleLoading(true);
    try {
      const updated = await updateSchedule({ hour_utc: hour, minute_utc: minute });
      setSchedule(updated);
    } catch (err) {
      console.error(err);
    } finally {
      setScheduleLoading(false);
    }
  }

  // Poll active crawl job
  useEffect(() => {
    if (!activeJobId) return;

    const poll = async () => {
      try {
        const status = await getCrawlStatus(activeJobId);
        setActiveJob(status);
        if (status.status === "complete" || status.status === "stopped" || status.status === "error") {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
          loadPages();
          loadChanges();
        }
      } catch { /* ignore */ }
    };

    poll();
    pollRef.current = setInterval(poll, 2000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [activeJobId]);

  async function handleStartCrawl() {
    try {
      const { job_id } = await startCrawl(activeProject?.id, autoIngest);
      setActiveJobId(job_id);
      setActiveJob(null);
    } catch (err) {
      console.error(err);
    }
  }

  async function handleStopCrawl() {
    if (activeJobId) await stopCrawl(activeJobId);
  }

  async function handleAddPage() {
    if (!newUrl.trim()) return;
    try {
      await addMonitoredPage(newUrl.trim(), activeProject?.id);
      setNewUrl("");
      loadPages();
    } catch (err) {
      console.error(err);
    }
  }

  async function handleRemovePage(pageId: string) {
    try {
      await removeMonitoredPage(pageId);
      loadPages();
    } catch (err) {
      console.error(err);
    }
  }

  const isRunning = activeJob?.status === "running" || activeJob?.status === "starting";
  const isComplete = activeJob?.status === "complete";
  const progressPct = activeJob && activeJob.total_pages > 0
    ? Math.min(100, (activeJob.pages_crawled / activeJob.total_pages) * 100)
    : 0;

  const crawlStats = [
    { label: "Pages Monitored", value: pages.length, icon: Eye, color: "text-indigo-600", bg: "bg-indigo-50" },
    { label: "Changes Detected", value: activeJob?.pages_modified ?? changes.length, icon: RefreshCw, color: "text-amber-600", bg: "bg-amber-50" },
    { label: "Auto-Ingested", value: activeJob?.auto_ingested ?? 0, icon: ArrowDownToLine, color: "text-emerald-600", bg: "bg-emerald-50" },
    { label: "Errors", value: activeJob?.pages_error ?? pages.filter(p => p.status === "error").length, icon: AlertTriangle, color: "text-red-600", bg: "bg-red-50" },
  ];

  return (
    <div className="space-y-6">
      {/* Controls */}
      <Card>
        <CardContent className="p-5">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-sm font-semibold">Page Change Detection</p>
              <p className="text-xs text-muted-foreground">
                Crawl {pages.length > 0 ? pages.length : "65+"} monitored DOR pages, detect content changes via MD5 hashing,
                and auto-ingest updates.
              </p>
            </div>
            <div className="flex items-center gap-3 shrink-0">
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input
                  type="checkbox"
                  checked={autoIngest}
                  onChange={(e) => setAutoIngest(e.target.checked)}
                  disabled={isRunning}
                  className="rounded"
                />
                <span className="text-xs text-muted-foreground">Auto-ingest</span>
              </label>
              <Button onClick={handleStartCrawl} disabled={isRunning} className="gap-2">
                {isRunning ? <Loader2 className="h-4 w-4 animate-spin" /> : <Radar className="h-4 w-4" />}
                {isRunning ? "Crawling..." : "Run Crawl"}
              </Button>
              {isRunning && (
                <Button variant="destructive" size="sm" onClick={handleStopCrawl} className="gap-1.5">
                  <Square className="h-3 w-3" />
                  Stop
                </Button>
              )}
            </div>
          </div>

          {/* Progress */}
          {activeJob && (
            <div className="mt-4 space-y-2">
              <div className="flex justify-between text-xs text-muted-foreground">
                <span>
                  {activeJob.pages_crawled} / {activeJob.total_pages} pages
                  {activeJob.current_url && (
                    <span className="ml-2 text-muted-foreground/60 truncate inline-block max-w-[300px] align-bottom">
                      {activeJob.current_url}
                    </span>
                  )}
                </span>
                <span>{formatElapsed(activeJob.elapsed_seconds)}</span>
              </div>
              <div className="w-full bg-muted rounded-full h-2 overflow-hidden">
                <div
                  className={`h-2 rounded-full transition-all duration-500 ${
                    isRunning ? "bg-primary animate-pulse" : isComplete ? "bg-emerald-500" : "bg-red-500"
                  }`}
                  style={{ width: `${progressPct}%` }}
                />
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Daily Schedule */}
      {schedule && (
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className={`flex h-8 w-8 items-center justify-center rounded-lg ${schedule.enabled ? "bg-emerald-50" : "bg-muted"}`}>
                  <Timer className={`h-4 w-4 ${schedule.enabled ? "text-emerald-600" : "text-muted-foreground"}`} />
                </div>
                <div>
                  <p className="text-sm font-medium">Automated Crawl Schedule</p>
                  <p className="text-xs text-muted-foreground">
                    {schedule.enabled
                      ? schedule.runs_per_day >= 2
                        ? `Runs ${schedule.runs_per_day}x daily at ${String(schedule.hour_utc).padStart(2, "0")}:00 & ${String((schedule.hour_utc + 12) % 24).padStart(2, "0")}:00 UTC`
                        : `Runs daily at ${String(schedule.hour_utc).padStart(2, "0")}:${String(schedule.minute_utc).padStart(2, "0")} UTC`
                      : "Disabled"}
                    {schedule.next_run_at && schedule.enabled && (
                      <span className="ml-1.5">
                        — next run {formatDate(schedule.next_run_at)}
                      </span>
                    )}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {schedule.enabled && (
                  <>
                    <select
                      value={schedule.runs_per_day}
                      onChange={(e) => {
                        const val = Number(e.target.value);
                        setScheduleLoading(true);
                        updateSchedule({ runs_per_day: val })
                          .then(setSchedule)
                          .catch(console.error)
                          .finally(() => setScheduleLoading(false));
                      }}
                      disabled={scheduleLoading}
                      className="rounded-md border px-2 py-1.5 text-xs bg-background"
                    >
                      <option value={1}>1x/day</option>
                      <option value={2}>2x/day</option>
                    </select>
                    <select
                      value={`${schedule.hour_utc}:${schedule.minute_utc}`}
                      onChange={(e) => {
                        const [h, m] = e.target.value.split(":").map(Number);
                        handleScheduleTimeChange(h, m);
                      }}
                      disabled={scheduleLoading}
                      className="rounded-md border px-2 py-1.5 text-xs bg-background"
                    >
                      {[0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22].map((h) => (
                        <option key={h} value={`${h}:0`}>
                          {String(h).padStart(2, "0")}:00 UTC
                        </option>
                      ))}
                    </select>
                  </>
                )}
                <button
                  onClick={() => handleScheduleToggle(!schedule.enabled)}
                  disabled={scheduleLoading}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                    schedule.enabled ? "bg-emerald-500" : "bg-muted-foreground/30"
                  }`}
                >
                  <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                      schedule.enabled ? "translate-x-6" : "translate-x-1"
                    }`}
                  />
                </button>
              </div>
            </div>
            {schedule.last_run_at && (
              <div className="mt-2 flex items-center gap-2 text-xs text-muted-foreground border-t pt-2">
                <span>Last run: {formatDate(schedule.last_run_at)}</span>
                {schedule.last_run_status && (
                  <Badge variant={schedule.last_run_status === "complete" ? "secondary" : "destructive"} className="text-xs">
                    {schedule.last_run_status}
                  </Badge>
                )}
                {schedule.last_run_changes > 0 && (
                  <span>{schedule.last_run_changes} changes</span>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Stat cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {crawlStats.map(({ label, value, icon: Icon, color, bg }) => (
          <Card key={label}>
            <CardContent className="p-4">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-xs text-muted-foreground">{label}</p>
                  <p className="text-2xl font-bold tracking-tight mt-1">{value}</p>
                </div>
                <div className={`flex h-8 w-8 items-center justify-center rounded-lg ${bg}`}>
                  <Icon className={`h-4 w-4 ${color}`} />
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Crawl results — changes detected */}
      {activeJob && isComplete && activeJob.changes.length > 0 && (
        <div className="space-y-3">
          <h3 className="text-sm font-semibold flex items-center gap-2">
            <RefreshCw className="h-4 w-4 text-amber-500" />
            Changes Detected This Crawl
          </h3>
          <div className="space-y-2">
            {activeJob.changes.map((change, i) => (
              <div key={i} className="rounded-lg border p-3.5 hover:bg-muted/50 transition-colors">
                <div className="flex items-center gap-2 mb-1">
                  {changeTypeBadge(change.type)}
                  {change.is_substantive && (
                    <Badge variant="outline" className="text-xs text-primary border-primary/30">Substantive</Badge>
                  )}
                  <span className="text-sm font-medium truncate">{change.title}</span>
                </div>
                <a
                  href={change.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-muted-foreground hover:text-primary truncate block"
                >
                  {change.url}
                  <ExternalLink className="inline h-2.5 w-2.5 ml-1 opacity-50" />
                </a>
                {change.summary && (
                  <p className="text-xs text-muted-foreground mt-1">{change.summary}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recent change history from DB */}
      {changes.length > 0 && (
        <div className="space-y-3">
          <h3 className="text-sm font-semibold flex items-center gap-2">
            <Clock className="h-4 w-4 text-muted-foreground" />
            Recent Changes
            {changes.filter(c => !c.review_status || c.review_status === "pending").length > 0 && (
              <Badge className="bg-amber-100 text-amber-700 border-amber-200 text-xs">
                {changes.filter(c => !c.review_status || c.review_status === "pending").length} pending
              </Badge>
            )}
          </h3>
          <div className="space-y-2">
            {changes.map((change) => {
              const isPending = !change.review_status || change.review_status === "pending";
              const isApproved = change.review_status === "approved";
              const isDismissed = change.review_status === "dismissed";

              return (
                <div key={change.id} className={`rounded-lg border p-3 transition-colors ${isPending ? "border-amber-200 bg-amber-50/30" : "hover:bg-muted/50"}`}>
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      {changeTypeBadge(change.change_type)}
                      <span className="text-sm font-medium truncate">{change.title || change.url}</span>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      {isApproved && (
                        <Badge className="bg-emerald-100 text-emerald-700 border-emerald-200 text-xs">Ingested</Badge>
                      )}
                      {isDismissed && (
                        <Badge variant="secondary" className="text-xs">Dismissed</Badge>
                      )}
                      {isPending && (
                        <>
                          <Button
                            size="sm"
                            variant="outline"
                            className="h-7 text-xs gap-1 border-emerald-300 text-emerald-700 hover:bg-emerald-50"
                            onClick={async () => {
                              try {
                                await approveChange(change.id);
                                loadChanges();
                              } catch (err) { console.error(err); }
                            }}
                          >
                            <CheckCircle2 className="h-3 w-3" />
                            Approve
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            className="h-7 text-xs text-muted-foreground hover:text-red-500"
                            onClick={async () => {
                              try {
                                await dismissChange(change.id);
                                loadChanges();
                              } catch (err) { console.error(err); }
                            }}
                          >
                            <XCircle className="h-3 w-3" />
                          </Button>
                        </>
                      )}
                      <span className="text-xs text-muted-foreground">
                        {formatDate(change.detected_at)}
                      </span>
                    </div>
                  </div>
                  {change.summary && (
                    <p className="text-xs text-muted-foreground mt-1 ml-0.5">{change.summary}</p>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Monitored pages toggle */}
      <div className="space-y-3">
        <button
          onClick={() => setShowPages(!showPages)}
          className="flex items-center gap-2 text-sm font-semibold hover:text-primary transition-colors"
        >
          <Eye className="h-4 w-4 text-muted-foreground" />
          Monitored Pages ({pages.length})
          <span className="text-xs text-muted-foreground font-normal">
            {showPages ? "Hide" : "Show"}
          </span>
        </button>

        {showPages && (
          <div className="space-y-3">
            {/* Add page */}
            <div className="flex gap-2">
              <input
                type="text"
                value={newUrl}
                onChange={(e) => setNewUrl(e.target.value)}
                placeholder="https://dor.wa.gov/..."
                className="flex-1 rounded-lg border px-3 py-2 text-sm bg-background"
                onKeyDown={(e) => e.key === "Enter" && handleAddPage()}
              />
              <Button size="sm" onClick={handleAddPage} disabled={!newUrl.trim()} className="gap-1.5">
                <Plus className="h-3.5 w-3.5" />
                Add
              </Button>
            </div>

            {/* Pages list */}
            <div className="rounded-lg border divide-y max-h-[400px] overflow-y-auto">
              {loadingPages ? (
                <div className="p-8 text-center text-sm text-muted-foreground">Loading...</div>
              ) : pages.length === 0 ? (
                <div className="p-8 text-center text-sm text-muted-foreground">
                  No pages registered yet. Run a crawl to populate the baseline.
                </div>
              ) : (
                pages.map((page) => (
                  <div key={page.id} className="flex items-center justify-between p-3 hover:bg-muted/30 transition-colors group">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 mb-0.5">
                        <span className={`h-2 w-2 rounded-full shrink-0 ${statusDot(page.status)}`} />
                        <span className="text-sm font-medium truncate">
                          {page.title || page.url}
                        </span>
                        {page.category && (
                          <Badge variant="secondary" className="text-xs shrink-0">{page.category}</Badge>
                        )}
                      </div>
                      <div className="flex items-center gap-3 text-xs text-muted-foreground ml-4">
                        <a href={page.url} target="_blank" rel="noopener noreferrer" className="hover:text-primary truncate max-w-[300px]">
                          {page.url}
                        </a>
                        <span className="shrink-0">Checked: {formatDate(page.last_checked_at)}</span>
                        {page.last_changed_at && page.last_changed_at !== page.last_checked_at && (
                          <span className="shrink-0 text-amber-600">Changed: {formatDate(page.last_changed_at)}</span>
                        )}
                        {page.error_message && (
                          <span className="text-red-500 truncate max-w-[200px]">{page.error_message}</span>
                        )}
                      </div>
                    </div>
                    <button
                      onClick={() => handleRemovePage(page.id)}
                      className="opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-red-500 p-1"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>
        )}
      </div>

      {/* Empty state */}
      {!activeJob && changes.length === 0 && pages.length === 0 && (
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-muted mb-4">
            <Radar className="h-7 w-7 text-muted-foreground" />
          </div>
          <p className="text-sm font-medium">No crawl activity yet</p>
          <p className="text-xs text-muted-foreground mt-1 max-w-sm">
            Click &quot;Run Crawl&quot; to scan 65+ DOR pages for content changes.
            First run will establish a baseline for future change detection.
          </p>
        </div>
      )}
    </div>
  );
}

// ==========================================================================
// URL Discovery Tab (Perplexity — existing functionality)
// ==========================================================================

const RECENCY_OPTIONS = [
  { value: "week", label: "Past Week" },
  { value: "month", label: "Past Month" },
  { value: "year", label: "Past Year" },
];

function categoryColor(category: string): string {
  if (category.includes("RCW")) return "bg-rose-500";
  if (category.includes("WAC")) return "bg-violet-500";
  if (category.includes("ETA")) return "bg-amber-500";
  if (category.includes("WTD") || category.includes("Determination")) return "bg-blue-500";
  if (category.includes("Interim")) return "bg-yellow-500";
  if (category.includes("Special Notice")) return "bg-teal-500";
  if (category.includes("Industry")) return "bg-cyan-500";
  return "bg-slate-500";
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

function UrlDiscoveryTab() {
  const { activeProject } = useProject();
  const [recency, setRecency] = useState("month");
  const [autoIngest, setAutoIngest] = useState(false);
  const [generateSummary, setGenerateSummary] = useState(true);
  const [queries, setQueries] = useState<MonitorQuery[]>([]);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [activeJob, setActiveJob] = useState<MonitorJob | null>(null);
  const [jobs, setJobs] = useState<MonitorJob[]>([]);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    getMonitorQueries().then(setQueries).catch(() => {});
    getMonitorJobs().then(setJobs).catch(() => {});
  }, []);

  useEffect(() => {
    if (!activeJobId) return;
    const poll = async () => {
      try {
        const status = await getMonitorStatus(activeJobId);
        setActiveJob(status);
        if (status.status === "complete" || status.status === "stopped" || status.status === "error") {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
          getMonitorJobs().then(setJobs).catch(() => {});
        }
      } catch { /* ignore */ }
    };
    poll();
    pollRef.current = setInterval(poll, 2000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [activeJobId]);

  async function handleStart() {
    try {
      const { job_id } = await startMonitor(activeProject?.id, recency, autoIngest, generateSummary);
      setActiveJobId(job_id);
      setActiveJob(null);
    } catch (err) {
      console.error(err);
    }
  }

  async function handleStop() {
    if (activeJobId) await stopMonitor(activeJobId);
  }

  const isRunning = activeJob?.status === "running" || activeJob?.status === "starting";
  const isComplete = activeJob?.status === "complete";
  const progressPct = activeJob && activeJob.total_queries > 0
    ? Math.min(100, (activeJob.queries_completed / activeJob.total_queries) * 100)
    : 0;
  const hasResults = activeJob && (isComplete || activeJob.status === "stopped");

  return (
    <div className="space-y-6">
      {/* Configure */}
      <Card>
        <CardContent className="p-5 space-y-4">
          <div>
            <p className="text-sm font-semibold">Perplexity URL Discovery</p>
            <p className="text-xs text-muted-foreground">
              Use Perplexity AI to search for new content across WA tax authority sites
              (dor.wa.gov, app.leg.wa.gov, taxpedia.dor.wa.gov).
            </p>
          </div>

          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1.5 block">Recency</label>
            <div className="flex gap-2">
              {RECENCY_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => setRecency(opt.value)}
                  disabled={isRunning}
                  className={`px-3 py-1.5 rounded-full text-sm border transition-colors ${
                    recency === opt.value
                      ? "bg-primary text-primary-foreground border-primary"
                      : "bg-background border-border text-muted-foreground hover:border-primary/30"
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          <div className="flex flex-wrap gap-4">
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" checked={autoIngest} onChange={(e) => setAutoIngest(e.target.checked)} disabled={isRunning} className="rounded" />
              <span className="text-muted-foreground">Auto-ingest</span>
            </label>
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" checked={generateSummary} onChange={(e) => setGenerateSummary(e.target.checked)} disabled={isRunning} className="rounded" />
              <span className="text-muted-foreground">AI summary</span>
            </label>
          </div>

          {queries.length > 0 && (
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1.5 block">
                Searches ({queries.length})
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

          <div className="flex gap-2">
            <Button onClick={handleStart} disabled={isRunning} className="gap-2">
              {isRunning ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
              {isRunning ? "Searching..." : "Search"}
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

      {/* Progress */}
      {activeJob && (
        <div className="space-y-3">
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>{activeJob.queries_completed} / {activeJob.total_queries} queries</span>
            <span>{formatElapsed(activeJob.elapsed_seconds)}</span>
          </div>
          <div className="w-full bg-muted rounded-full h-2 overflow-hidden">
            <div
              className={`h-2 rounded-full transition-all duration-500 ${
                isRunning ? "bg-primary animate-pulse" : isComplete ? "bg-emerald-500" : "bg-red-500"
              }`}
              style={{ width: `${progressPct}%` }}
            />
          </div>
          {isRunning && activeJob.current_query && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-primary" />
              </span>
              <span className="truncate">{activeJob.current_query}</span>
            </div>
          )}

          <div className="grid grid-cols-4 gap-3">
            {[
              { label: "Found", value: activeJob.urls_found },
              { label: "Existing", value: activeJob.existing_urls },
              { label: "New", value: activeJob.new_urls },
              { label: "Ingested", value: activeJob.ingested },
            ].map(({ label, value }) => (
              <Card key={label}>
                <CardContent className="p-3 text-center">
                  <p className="text-xs text-muted-foreground">{label}</p>
                  <p className="text-xl font-bold">{value}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}

      {/* Results */}
      {hasResults && (
        <div className="space-y-3">
          {activeJob!.summary && (
            <Card className="border-primary/20 bg-primary/5">
              <CardContent className="p-5">
                <div className="flex items-center gap-2 mb-3">
                  <Sparkles className="h-3.5 w-3.5 text-primary" />
                  <span className="text-sm font-semibold">AI Summary</span>
                </div>
                <p className="text-sm text-muted-foreground leading-relaxed whitespace-pre-wrap">
                  {activeJob!.summary}
                </p>
              </CardContent>
            </Card>
          )}

          {activeJob!.new_url_list.length > 0 ? (
            <div className="space-y-2">
              <p className="text-xs font-medium text-muted-foreground">New pages discovered</p>
              {activeJob!.new_url_list.map((item: MonitorNewUrl, i: number) => (
                <div key={i} className="rounded-lg border p-3.5 hover:bg-muted/50 transition-colors">
                  <div className="flex items-center gap-2 mb-1">
                    <a href={item.url} target="_blank" rel="noopener noreferrer" className="text-sm font-medium hover:text-primary truncate">
                      {item.title || item.url}
                      <ExternalLink className="inline h-3 w-3 ml-1 opacity-50" />
                    </a>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant="secondary" className="gap-1 text-xs pl-1.5">
                      <span className={`h-1.5 w-1.5 rounded-full ${categoryColor(item.category)}`} />
                      {item.category}
                    </Badge>
                    {statusBadge(item.status)}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="flex flex-col items-center py-8 text-center">
              <CheckCircle2 className="h-8 w-8 text-emerald-500 mb-2" />
              <p className="text-sm font-medium">Up to date</p>
              <p className="text-xs text-muted-foreground">No new content found</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ==========================================================================
// Main Page with Tabs
// ==========================================================================

export default function MonitorPage() {
  const [activeTab, setActiveTab] = useState<"crawl" | "discover">("crawl");

  return (
    <div className="max-w-4xl space-y-6">
      {/* Header */}
      <div>
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/10 mb-3">
          <Radar className="h-6 w-6 text-primary" />
        </div>
        <h2 className="text-2xl font-bold tracking-tight">Monitor</h2>
        <p className="text-muted-foreground mt-1">
          Track changes on WA DOR pages and discover new content across tax authority sites.
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 p-1 bg-muted rounded-lg w-fit">
        <button
          onClick={() => setActiveTab("crawl")}
          className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
            activeTab === "crawl"
              ? "bg-background text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground"
          }`}
        >
          <Radar className="inline h-4 w-4 mr-1.5 -mt-0.5" />
          Page Monitor
        </button>
        <button
          onClick={() => setActiveTab("discover")}
          className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
            activeTab === "discover"
              ? "bg-background text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground"
          }`}
        >
          <Search className="inline h-4 w-4 mr-1.5 -mt-0.5" />
          URL Discovery
        </button>
      </div>

      {/* Tab content */}
      {activeTab === "crawl" ? <PageMonitorTab /> : <UrlDiscoveryTab />}
    </div>
  );
}
