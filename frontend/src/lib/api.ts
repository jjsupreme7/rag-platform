const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

// ---------------------------------------------------------------------------
// Project CRUD
// ---------------------------------------------------------------------------

export interface Project {
  id: string;
  name: string;
  description: string | null;
  system_prompt: string;
  chat_model: string;
  embedding_model: string;
  created_at: string;
}

export async function fetchProjects(): Promise<Project[]> {
  const res = await fetch(`${API_BASE}/api/projects`);
  if (!res.ok) throw new Error("Failed to fetch projects");
  return res.json();
}

export async function createProject(data: {
  name: string;
  description?: string;
  system_prompt?: string;
  chat_model?: string;
  embedding_model?: string;
}): Promise<Project> {
  const res = await fetch(`${API_BASE}/api/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to create project");
  return res.json();
}

export async function updateProject(
  id: string,
  data: Partial<{
    name: string;
    description: string;
    system_prompt: string;
    chat_model: string;
    embedding_model: string;
  }>
): Promise<Project> {
  const res = await fetch(`${API_BASE}/api/projects/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to update project");
  return res.json();
}

export async function deleteProject(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/projects/${id}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Failed to delete project");
}

// ---------------------------------------------------------------------------
// Stats
// ---------------------------------------------------------------------------

export async function fetchStats(projectId?: string): Promise<Record<string, number | null>> {
  const params = new URLSearchParams();
  if (projectId) params.set("project_id", projectId);
  const res = await fetch(`${API_BASE}/api/stats?${params}`);
  if (!res.ok) throw new Error("Failed to fetch stats");
  return res.json();
}

// ---------------------------------------------------------------------------
// Documents
// ---------------------------------------------------------------------------

export interface Document {
  id: string;
  document_type: string;
  source_type: string | null;
  title: string;
  source_file: string;
  source_url: string | null;
  citation: string;
  law_category: string;
  total_chunks: number;
  processing_status: string;
  created_at: string;
  topic_tags: string[] | null;
}

export interface DocumentsResponse {
  documents: Document[];
  total: number;
}

export async function fetchDocuments(
  offset = 0,
  limit = 50,
  category?: string,
  projectId?: string,
  sourceType?: string
): Promise<DocumentsResponse> {
  const params = new URLSearchParams({
    offset: String(offset),
    limit: String(limit),
  });
  if (category) params.set("category", category);
  if (projectId) params.set("project_id", projectId);
  if (sourceType) params.set("source_type", sourceType);
  const res = await fetch(`${API_BASE}/api/documents?${params}`);
  if (!res.ok) throw new Error("Failed to fetch documents");
  return res.json();
}

export async function fetchCategories(projectId?: string): Promise<Record<string, number>> {
  const params = new URLSearchParams();
  if (projectId) params.set("project_id", projectId);
  const res = await fetch(`${API_BASE}/api/documents/categories?${params}`);
  if (!res.ok) throw new Error("Failed to fetch categories");
  const data = await res.json();
  return data.categories;
}

export async function fetchSourceTypes(projectId?: string): Promise<Record<string, number>> {
  const params = new URLSearchParams();
  if (projectId) params.set("project_id", projectId);
  const res = await fetch(`${API_BASE}/api/documents/source-types?${params}`);
  if (!res.ok) throw new Error("Failed to fetch source types");
  const data = await res.json();
  return data.source_types;
}

export interface RecentChat {
  id: string;
  question: string;
  chat_model: string | null;
  response_time_ms: number | null;
  sources_count: number | null;
  is_error: boolean;
  created_at: string;
}

export async function fetchRecentChats(limit = 5, projectId?: string): Promise<RecentChat[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (projectId) params.set("project_id", projectId);
  const res = await fetch(`${API_BASE}/api/chat/recent?${params}`);
  if (!res.ok) throw new Error("Failed to fetch recent chats");
  const data = await res.json();
  return data.chats;
}

// ---------------------------------------------------------------------------
// Document Detail (with chunks)
// ---------------------------------------------------------------------------

export interface Chunk {
  id: string;
  chunk_number: number;
  chunk_text: string;
  citation: string;
  section_title: string | null;
  law_category: string;
}

export interface DocumentDetail {
  document: Document;
  chunks: Chunk[];
}

export async function fetchDocument(docId: string): Promise<DocumentDetail> {
  const res = await fetch(`${API_BASE}/api/documents/${docId}`);
  if (!res.ok) throw new Error("Failed to fetch document");
  return res.json();
}

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------

export interface SearchResult {
  id: string;
  document_id: string;
  chunk_text: string;
  citation: string;
  section_title: string | null;
  law_category: string;
  similarity: number;
  source_file: string;
  file_url: string | null;
  source_url: string | null;
  topic_tags: string[] | null;
  tax_types: string[] | null;
}

export interface SearchResponse {
  query: string;
  results: SearchResult[];
  count: number;
}

export async function searchDocuments(
  query: string,
  topK = 5,
  threshold = 0.3,
  projectId?: string
): Promise<SearchResponse> {
  const res = await fetch(`${API_BASE}/api/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, top_k: topK, threshold, project_id: projectId }),
  });
  if (!res.ok) throw new Error("Failed to search");
  return res.json();
}

// ---------------------------------------------------------------------------
// Ingest
// ---------------------------------------------------------------------------

export interface UploadResult {
  document_id: string | null;
  title: string;
  chunks_created: number;
  status: string;
  error?: string;
}

export async function uploadPDF(
  file: File,
  category: string,
  citation?: string,
  projectId?: string
): Promise<UploadResult> {
  const form = new FormData();
  form.append("file", file);
  form.append("category", category);
  if (citation) form.append("citation", citation);
  if (projectId) form.append("project_id", projectId);
  const res = await fetch(`${API_BASE}/api/ingest/pdf`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) throw new Error("Failed to upload PDF");
  return res.json();
}

// ---------------------------------------------------------------------------
// Chat
// ---------------------------------------------------------------------------

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatSource {
  citation: string;
  similarity: number;
  source_url?: string | null;
  source?: "local" | "perplexity";
}

export async function sendChatMessage(
  message: string,
  history: ChatMessage[],
  onChunk: (text: string) => void,
  onSources: (sources: ChatSource[]) => void,
  projectId?: string,
  modelOverride?: string,
): Promise<void> {
  const body: Record<string, unknown> = { message, history, project_id: projectId };
  if (modelOverride) body.model_override = modelOverride;
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error("Failed to send message");

  // Parse sources from header
  const sourcesHeader = res.headers.get("X-Sources");
  if (sourcesHeader) {
    try {
      onSources(JSON.parse(sourcesHeader));
    } catch { /* ignore */ }
  }

  // Stream the response body
  const reader = res.body?.getReader();
  if (!reader) return;
  const decoder = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    onChunk(decoder.decode(value));
  }
}

// ---------------------------------------------------------------------------
// Web Scraping
// ---------------------------------------------------------------------------

export interface DiscoverResult {
  base_url: string;
  total_discovered: number;
  total_filtered: number;
  categories: Record<string, number>;
  sample_urls: string[];
}

export interface ScrapeJob {
  job_id: string;
  status: string;
  base_url: string;
  total_discovered: number;
  total_filtered: number;
  scraped: number;
  failed: number;
  documents_created: number;
  chunks_created: number;
  current_url: string;
  elapsed_seconds: number;
  error?: string;
}

export async function discoverUrls(
  url: string,
  includePatterns?: string[]
): Promise<DiscoverResult> {
  const res = await fetch(`${API_BASE}/api/scrape/discover`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, include_patterns: includePatterns }),
  });
  if (!res.ok) throw new Error("Failed to discover URLs");
  return res.json();
}

export async function startScrape(
  url: string,
  projectId?: string,
  includePatterns?: string[]
): Promise<{ job_id: string }> {
  const res = await fetch(`${API_BASE}/api/scrape/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      url,
      project_id: projectId,
      include_patterns: includePatterns,
    }),
  });
  if (!res.ok) throw new Error("Failed to start scrape");
  return res.json();
}

export async function getScrapeStatus(jobId: string): Promise<ScrapeJob> {
  const res = await fetch(`${API_BASE}/api/scrape/status/${jobId}`);
  if (!res.ok) throw new Error("Failed to get scrape status");
  return res.json();
}

export async function getScrapeJobs(): Promise<ScrapeJob[]> {
  const res = await fetch(`${API_BASE}/api/scrape/jobs`);
  if (!res.ok) throw new Error("Failed to get scrape jobs");
  return res.json();
}

export async function stopScrape(jobId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/scrape/stop/${jobId}`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to stop scrape");
}

// ---------------------------------------------------------------------------
// Website Monitor (Perplexity)
// ---------------------------------------------------------------------------

export interface MonitorQuery {
  id: string;
  label: string;
}

export interface MonitorNewUrl {
  url: string;
  title: string;
  snippet: string;
  date: string | null;
  category: string;
  status: string;
  chunks_created?: number;
}

export interface MonitorJob {
  job_id: string;
  status: string;
  total_queries: number;
  queries_completed: number;
  urls_found: number;
  new_urls: number;
  existing_urls: number;
  ingested: number;
  ingest_failed: number;
  current_query: string;
  elapsed_seconds: number;
  new_url_list: MonitorNewUrl[];
  summary: string | null;
  error?: string;
}

export async function getMonitorQueries(): Promise<MonitorQuery[]> {
  const res = await fetch(`${API_BASE}/api/monitor/queries`);
  if (!res.ok) throw new Error("Failed to fetch monitor queries");
  return res.json();
}

export async function startMonitor(
  projectId?: string,
  recencyFilter: string = "month",
  autoIngest: boolean = false,
  generateSummary: boolean = true,
): Promise<{ job_id: string }> {
  const res = await fetch(`${API_BASE}/api/monitor/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      project_id: projectId,
      recency_filter: recencyFilter,
      auto_ingest: autoIngest,
      generate_summary: generateSummary,
    }),
  });
  if (!res.ok) throw new Error("Failed to start monitor");
  return res.json();
}

export async function getMonitorStatus(jobId: string): Promise<MonitorJob> {
  const res = await fetch(`${API_BASE}/api/monitor/status/${jobId}`);
  if (!res.ok) throw new Error("Failed to get monitor status");
  return res.json();
}

export async function getMonitorJobs(): Promise<MonitorJob[]> {
  const res = await fetch(`${API_BASE}/api/monitor/jobs`);
  if (!res.ok) throw new Error("Failed to get monitor jobs");
  return res.json();
}

export async function stopMonitor(jobId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/monitor/stop/${jobId}`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to stop monitor");
}

// ---------------------------------------------------------------------------
// Page Monitor (DOR page-change detection)
// ---------------------------------------------------------------------------

export interface CrawlJob {
  job_id: string;
  status: string;
  total_pages: number;
  pages_crawled: number;
  pages_new: number;
  pages_modified: number;
  pages_unchanged: number;
  pages_error: number;
  substantive_changes: number;
  auto_ingested: number;
  new_wtds_found: number;
  new_wtds_ingested: number;
  news_releases: number;
  special_notices: number;
  current_url: string;
  elapsed_seconds: number;
  changes: CrawlChange[];
  errors: { url: string; error: string }[];
  error?: string;
}

export interface CrawlChange {
  url: string;
  type: string;
  title: string;
  summary: string;
  is_substantive?: boolean;
}

export interface MonitoredPage {
  id: string;
  url: string;
  category: string | null;
  title: string | null;
  content_hash: string | null;
  last_checked_at: string | null;
  last_changed_at: string | null;
  status: string;
  error_message: string | null;
  created_at: string;
}

export interface ChangeLogEntry {
  id: string;
  page_state_id: string | null;
  url: string;
  change_type: string;
  title: string | null;
  summary: string | null;
  is_substantive: boolean;
  diff_additions: number;
  diff_deletions: number;
  auto_ingested: boolean;
  review_status: string | null;
  last_modified: string | null;
  detected_at: string;
}

export async function startCrawl(
  projectId?: string,
  autoIngest: boolean = true
): Promise<{ job_id: string }> {
  const res = await fetch(`${API_BASE}/api/monitor/crawl`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: projectId, auto_ingest: autoIngest }),
  });
  if (!res.ok) throw new Error("Failed to start crawl");
  return res.json();
}

export async function getCrawlStatus(jobId: string): Promise<CrawlJob> {
  const res = await fetch(`${API_BASE}/api/monitor/crawl/status/${jobId}`);
  if (!res.ok) throw new Error("Failed to get crawl status");
  return res.json();
}

export async function getCrawlJobs(): Promise<CrawlJob[]> {
  const res = await fetch(`${API_BASE}/api/monitor/crawl/jobs`);
  if (!res.ok) throw new Error("Failed to get crawl jobs");
  return res.json();
}

export async function stopCrawl(jobId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/monitor/crawl/stop/${jobId}`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to stop crawl");
}

export async function getMonitoredPages(
  projectId?: string
): Promise<{ pages: MonitoredPage[]; total: number }> {
  const params = new URLSearchParams();
  if (projectId) params.set("project_id", projectId);
  const res = await fetch(`${API_BASE}/api/monitor/pages?${params}`);
  if (!res.ok) throw new Error("Failed to get monitored pages");
  return res.json();
}

export async function addMonitoredPage(
  url: string,
  projectId?: string,
  category?: string
): Promise<MonitoredPage> {
  const res = await fetch(`${API_BASE}/api/monitor/pages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, project_id: projectId, category }),
  });
  if (!res.ok) throw new Error("Failed to add monitored page");
  return res.json();
}

export async function removeMonitoredPage(pageId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/monitor/pages/${pageId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Failed to remove monitored page");
}

export async function getMonitorChanges(
  projectId?: string,
  limit = 50,
  offset = 0,
  changeType?: string,
  substantiveOnly = false
): Promise<{ changes: ChangeLogEntry[]; total: number }> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  if (projectId) params.set("project_id", projectId);
  if (changeType) params.set("change_type", changeType);
  if (substantiveOnly) params.set("substantive_only", "true");
  const res = await fetch(`${API_BASE}/api/monitor/changes?${params}`);
  if (!res.ok) throw new Error("Failed to get changes");
  return res.json();
}

export async function getRecentChanges(
  projectId?: string,
  limit = 10
): Promise<{ changes: ChangeLogEntry[] }> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (projectId) params.set("project_id", projectId);
  const res = await fetch(`${API_BASE}/api/monitor/changes/recent?${params}`);
  if (!res.ok) throw new Error("Failed to get recent changes");
  return res.json();
}

// ---------------------------------------------------------------------------
// Schedule (automated daily crawls)
// ---------------------------------------------------------------------------

export interface ScheduleConfig {
  id: string;
  enabled: boolean;
  hour_utc: number;
  minute_utc: number;
  runs_per_day: number;
  auto_ingest: boolean;
  project_id: string | null;
  last_run_at: string | null;
  last_run_status: string | null;
  last_run_changes: number;
  next_run_at: string | null;
  created_at: string;
  updated_at: string;
}

export async function getSchedule(): Promise<ScheduleConfig> {
  const res = await fetch(`${API_BASE}/api/monitor/schedule`);
  if (!res.ok) throw new Error("Failed to get schedule");
  return res.json();
}

export async function updateSchedule(data: {
  enabled?: boolean;
  hour_utc?: number;
  minute_utc?: number;
  runs_per_day?: number;
  auto_ingest?: boolean;
  project_id?: string;
}): Promise<ScheduleConfig> {
  const res = await fetch(`${API_BASE}/api/monitor/schedule`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to update schedule");
  return res.json();
}

export async function approveChange(changeId: string): Promise<{ status: string; ingested: boolean }> {
  const res = await fetch(`${API_BASE}/api/monitor/changes/${changeId}/approve`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to approve change");
  return res.json();
}

export async function dismissChange(changeId: string): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/api/monitor/changes/${changeId}/dismiss`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to dismiss change");
  return res.json();
}

export async function triggerScheduledCrawl(): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/api/monitor/schedule/run-now`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to trigger crawl");
  return res.json();
}
