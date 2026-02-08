const API_BASE = "http://localhost:8001";

export async function fetchStats(): Promise<Record<string, number | null>> {
  const res = await fetch(`${API_BASE}/api/stats`);
  if (!res.ok) throw new Error("Failed to fetch stats");
  return res.json();
}

export interface Document {
  id: string;
  document_type: string;
  title: string;
  source_file: string;
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
  category?: string
): Promise<DocumentsResponse> {
  const params = new URLSearchParams({
    offset: String(offset),
    limit: String(limit),
  });
  if (category) params.set("category", category);
  const res = await fetch(`${API_BASE}/api/documents?${params}`);
  if (!res.ok) throw new Error("Failed to fetch documents");
  return res.json();
}

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
  threshold = 0.3
): Promise<SearchResponse> {
  const res = await fetch(`${API_BASE}/api/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, top_k: topK, threshold }),
  });
  if (!res.ok) throw new Error("Failed to search");
  return res.json();
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatSource {
  citation: string;
  similarity: number;
}

export async function sendChatMessage(
  message: string,
  history: ChatMessage[],
  onChunk: (text: string) => void,
  onSources: (sources: ChatSource[]) => void,
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, history }),
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
