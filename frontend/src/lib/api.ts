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
}

export async function sendChatMessage(
  message: string,
  history: ChatMessage[],
  onChunk: (text: string) => void,
  onSources: (sources: ChatSource[]) => void,
  projectId?: string,
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, history, project_id: projectId }),
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
