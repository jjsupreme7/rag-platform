"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
} from "@/components/ui/card";
import {
  Globe,
  Loader2,
  Square,
  FileText,
  Clock,
  Database,
  AlertCircle,
  Search,
  Play,
  CheckCircle2,
  XCircle,
  Timer,
  Link as LinkIcon,
} from "lucide-react";
import {
  discoverUrls,
  startScrape,
  getScrapeStatus,
  getScrapeJobs,
  stopScrape,
  type DiscoverResult,
  type ScrapeJob,
} from "@/lib/api";
import { useProject } from "@/lib/project-context";

const CONTENT_CATEGORIES = [
  { key: "/laws-rules/", label: "Laws & Rules" },
  { key: "/taxes-rates/", label: "Tax Rates" },
  { key: "/education/", label: "Education" },
  { key: "/forms-publications/", label: "Forms & Pubs" },
  { key: ".pdf", label: "PDFs" },
];

const STAT_CARDS = [
  {
    key: "total_filtered",
    label: "URLs Found",
    icon: Globe,
    color: "text-indigo-600",
    bg: "bg-indigo-50",
    border: "border-indigo-100",
  },
  {
    key: "documents_created",
    label: "Documents",
    icon: FileText,
    color: "text-emerald-600",
    bg: "bg-emerald-50",
    border: "border-emerald-100",
  },
  {
    key: "chunks_created",
    label: "Chunks",
    icon: Database,
    color: "text-blue-600",
    bg: "bg-blue-50",
    border: "border-blue-100",
  },
  {
    key: "failed",
    label: "Failed",
    icon: AlertCircle,
    color: "text-red-600",
    bg: "bg-red-50",
    border: "border-red-100",
  },
];

function formatElapsed(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  if (mins === 0) return `${secs}s`;
  return `${mins}m ${secs}s`;
}

function formatRelativeTime(seconds: number): string {
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
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

export default function ScrapePage() {
  const { activeProject } = useProject();
  const [url, setUrl] = useState("https://dor.wa.gov");
  const [selectedCategories, setSelectedCategories] = useState<string[]>(
    CONTENT_CATEGORIES.map((c) => c.key)
  );

  // Discovery state
  const [discovering, setDiscovering] = useState(false);
  const [discovery, setDiscovery] = useState<DiscoverResult | null>(null);

  // Scraping state
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [activeJob, setActiveJob] = useState<ScrapeJob | null>(null);
  const [jobs, setJobs] = useState<ScrapeJob[]>([]);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Load past jobs on mount
  useEffect(() => {
    getScrapeJobs()
      .then(setJobs)
      .catch(() => {});
  }, []);

  // Poll active job status
  useEffect(() => {
    if (!activeJobId) return;

    const poll = async () => {
      try {
        const status = await getScrapeStatus(activeJobId);
        setActiveJob(status);
        if (
          status.status === "complete" ||
          status.status === "stopped" ||
          status.status === "error"
        ) {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
          getScrapeJobs()
            .then(setJobs)
            .catch(() => {});
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

  function toggleCategory(key: string) {
    setSelectedCategories((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]
    );
  }

  async function handleDiscover() {
    setDiscovering(true);
    setDiscovery(null);
    try {
      const result = await discoverUrls(url, selectedCategories);
      setDiscovery(result);
    } catch (err) {
      console.error(err);
    } finally {
      setDiscovering(false);
    }
  }

  async function handleStartScrape() {
    try {
      const { job_id } = await startScrape(
        url,
        activeProject?.id,
        selectedCategories
      );
      setActiveJobId(job_id);
      setActiveJob(null);
    } catch (err) {
      console.error(err);
    }
  }

  async function handleStop() {
    if (activeJobId) {
      await stopScrape(activeJobId);
    }
  }

  const isRunning =
    activeJob?.status === "running" || activeJob?.status === "starting";
  const progressPct =
    activeJob && activeJob.total_filtered > 0
      ? Math.min(100, (activeJob.scraped / activeJob.total_filtered) * 100)
      : 0;

  const pastJobs = jobs.filter((j) => j.job_id !== activeJobId).slice(0, 10);
  const hasActivity = !!discovery || !!activeJob || pastJobs.length > 0;

  return (
    <div className="max-w-4xl space-y-8">
      {/* Hero section */}
      <div>
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/10 mb-3">
          <Globe className="h-6 w-6 text-primary" />
        </div>
        <h2 className="text-2xl font-bold tracking-tight">Scrape Website</h2>
        <p className="text-muted-foreground mt-1">
          Crawl a website to discover and ingest content into your knowledge
          base via sitemap.xml.
        </p>
      </div>

      {/* Step 1: Configure */}
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <StepNumber n={1} active={!discovery && !activeJob} />
          <div>
            <p className="text-sm font-semibold">Configure</p>
            <p className="text-xs text-muted-foreground">
              Enter URL and select content filters
            </p>
          </div>
        </div>

        <Card className="ml-10">
          <CardContent className="p-5 space-y-4">
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1.5 block">
                Website URL
              </label>
              <Input
                placeholder="https://dor.wa.gov"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                disabled={isRunning}
                className="focus-visible:ring-primary/30 focus-visible:border-primary/50"
              />
            </div>

            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1.5 block">
                Content to include
              </label>
              <div className="flex flex-wrap gap-2">
                {CONTENT_CATEGORIES.map((cat) => (
                  <button
                    key={cat.key}
                    onClick={() => toggleCategory(cat.key)}
                    disabled={isRunning}
                    className={`px-3 py-1.5 rounded-full text-sm border transition-colors ${
                      selectedCategories.includes(cat.key)
                        ? "bg-primary text-primary-foreground border-primary"
                        : "bg-background border-border text-muted-foreground hover:border-primary/30 hover:bg-accent"
                    }`}
                  >
                    {cat.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex gap-2 pt-1">
              <Button
                onClick={handleDiscover}
                disabled={discovering || isRunning || !url.trim()}
                variant="outline"
                className="gap-2"
              >
                {discovering ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Search className="h-4 w-4" />
                )}
                {discovering ? "Discovering..." : "Discover Pages"}
              </Button>
              <Button
                onClick={handleStartScrape}
                disabled={isRunning || !url.trim()}
                className="gap-2"
              >
                {isRunning ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Play className="h-4 w-4" />
                )}
                {isRunning ? "Scraping..." : "Start Scraping"}
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

      {/* Step 2: Discovery Results */}
      {discovery && !activeJob && (
        <div className="space-y-4">
          <div className="flex items-center gap-3">
            <StepNumber n={2} active={true} />
            <div>
              <p className="text-sm font-semibold">Discovery Results</p>
              <p className="text-xs text-muted-foreground">
                {discovery.total_filtered.toLocaleString()} pages match your
                filters out of {discovery.total_discovered.toLocaleString()}{" "}
                total
              </p>
            </div>
          </div>

          <Card className="ml-10 border-emerald-200 bg-emerald-50/30">
            <CardContent className="p-5 space-y-4">
              <div className="flex flex-wrap gap-2">
                {Object.entries(discovery.categories)
                  .sort(([, a], [, b]) => b - a)
                  .map(([cat, count]) => (
                    <Badge
                      key={cat}
                      variant="secondary"
                      className="gap-1.5 pl-2"
                    >
                      <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                      {cat}: {count.toLocaleString()}
                    </Badge>
                  ))}
              </div>

              {discovery.sample_urls.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-muted-foreground mb-2">
                    Sample URLs
                  </p>
                  <div className="rounded-lg border bg-background overflow-hidden">
                    {discovery.sample_urls.map((u, i) => (
                      <div
                        key={i}
                        className={`flex items-center gap-2 px-3 py-1.5 text-xs text-muted-foreground ${
                          i % 2 === 0 ? "" : "bg-muted/30"
                        }`}
                      >
                        <LinkIcon className="h-3 w-3 shrink-0 text-muted-foreground/50" />
                        <span className="truncate font-mono">{u}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* Step 3: Scraping Progress */}
      {activeJob && (
        <div className="space-y-4">
          <div className="flex items-center gap-3">
            <StepNumber n={discovery ? 3 : 2} active={true} />
            <div>
              <p className="text-sm font-semibold">
                {isRunning ? "Scraping in Progress" : `Scrape ${activeJob.status === "complete" ? "Complete" : activeJob.status === "error" ? "Failed" : "Stopped"}`}
              </p>
              <p className="text-xs text-muted-foreground">
                Job {activeJob.job_id} &middot;{" "}
                {formatElapsed(activeJob.elapsed_seconds)}
              </p>
            </div>
          </div>

          <div className="ml-10 space-y-4">
            {/* Progress bar */}
            {activeJob.total_filtered > 0 && (
              <div>
                <div className="flex justify-between text-xs text-muted-foreground mb-1.5">
                  <span>
                    {activeJob.scraped.toLocaleString()} /{" "}
                    {activeJob.total_filtered.toLocaleString()} pages
                  </span>
                  <span className="font-medium">
                    {Math.round(progressPct)}%
                  </span>
                </div>
                <div className="w-full bg-muted rounded-full h-2.5 overflow-hidden">
                  <div
                    className={`h-2.5 rounded-full transition-all duration-500 ${
                      isRunning
                        ? "bg-gradient-to-r from-primary via-primary/80 to-primary animate-pulse"
                        : activeJob.status === "complete"
                          ? "bg-emerald-500"
                          : activeJob.status === "error"
                            ? "bg-red-500"
                            : "bg-yellow-500"
                    }`}
                    style={{ width: `${progressPct}%` }}
                  />
                </div>
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

            {/* Current URL */}
            {isRunning && activeJob.current_url && (
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-primary" />
                </span>
                <span className="truncate font-mono">
                  {activeJob.current_url}
                </span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Empty state */}
      {!hasActivity && (
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-muted mb-4">
            <Globe className="h-7 w-7 text-muted-foreground" />
          </div>
          <p className="text-sm font-medium">No scrape activity yet</p>
          <p className="text-xs text-muted-foreground mt-1 max-w-sm">
            Enter a website URL above and click &quot;Discover Pages&quot; to
            preview content, or &quot;Start Scraping&quot; to begin ingesting.
          </p>
        </div>
      )}

      {/* Job History */}
      {pastJobs.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <Clock className="h-4 w-4 text-muted-foreground" />
            <h3 className="text-sm font-medium">Job History</h3>
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
                    <p className="text-sm font-medium truncate">
                      {job.base_url}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {job.documents_created} docs &middot;{" "}
                      {job.chunks_created.toLocaleString()} chunks &middot;{" "}
                      {formatElapsed(job.elapsed_seconds)}
                    </p>
                  </div>
                </div>
                <div className="text-right shrink-0 ml-4">
                  <code className="text-xs text-muted-foreground">
                    {job.job_id}
                  </code>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
