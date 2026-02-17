"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Search, X } from "lucide-react";
import { searchDocuments, fetchTags, type SearchResult, type TagCount } from "@/lib/api";
import { useProject } from "@/lib/project-context";

export default function SearchPage() {
  const { activeProject } = useProject();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [tags, setTags] = useState<TagCount[]>([]);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [tagSearch, setTagSearch] = useState("");

  useEffect(() => {
    fetchTags(activeProject?.id, 50).then(setTags).catch(console.error);
  }, [activeProject?.id]);

  function toggleTag(tag: string) {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]
    );
  }

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    setSearched(true);
    try {
      const res = await searchDocuments(query, 8, 0.3, activeProject?.id, selectedTags.length > 0 ? selectedTags : undefined);
      setResults(res.results);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-4xl">
      <h2 className="text-2xl font-bold tracking-tight mb-1">Search Playground</h2>
      <p className="text-sm text-muted-foreground mb-6">
        Test vector search against your knowledge base. Results are ranked by
        cosine similarity.
      </p>

      <form onSubmit={handleSearch} className="flex gap-2 mb-8">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="e.g. Is cloud software taxable in Washington?"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="pl-10 focus-visible:ring-primary/30 focus-visible:border-primary/50"
          />
        </div>
        <Button type="submit" disabled={loading || !query.trim()}>
          {loading ? "Searching..." : "Search"}
        </Button>
      </form>

      {/* Tag scope filter */}
      {tags.length > 0 && (
        <div className="mb-6">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs font-medium text-muted-foreground">Scope to tags</span>
            {selectedTags.length > 0 && (
              <button
                onClick={() => setSelectedTags([])}
                className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-0.5"
              >
                <X className="h-3 w-3" /> Clear ({selectedTags.length})
              </button>
            )}
            <input
              type="text"
              placeholder="Filter tags..."
              value={tagSearch}
              onChange={(e) => setTagSearch(e.target.value)}
              className="px-2 py-0.5 text-xs border rounded-md bg-background w-40 ml-auto"
            />
          </div>
          <div className="flex flex-wrap gap-1.5">
            {(tagSearch
              ? tags.filter((t) => t.tag.toLowerCase().includes(tagSearch.toLowerCase()))
              : tags.slice(0, 15)
            ).map(({ tag, count }) => (
              <button
                key={tag}
                onClick={() => toggleTag(tag)}
                className={`px-2 py-0.5 rounded-full text-xs border transition-colors ${
                  selectedTags.includes(tag)
                    ? "bg-primary text-primary-foreground border-primary"
                    : "bg-background border-border hover:bg-accent"
                }`}
              >
                {tag} ({count})
              </button>
            ))}
          </div>
        </div>
      )}

      {loading && (
        <p className="text-muted-foreground">Embedding query and searching...</p>
      )}

      {!loading && searched && results.length === 0 && (
        <p className="text-muted-foreground">No results found.</p>
      )}

      {!loading && results.length > 0 && (
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">
            {results.length} results found
          </p>
          {results.map((result, i) => (
            <Card key={result.id} className="overflow-hidden transition-shadow hover:shadow-md">
              <div
                className="h-1"
                style={{
                  background: result.similarity > 0.6
                    ? "var(--primary)"
                    : result.similarity > 0.4
                      ? "oklch(0.65 0.19 160)"
                      : "oklch(0.70 0.18 50)",
                  opacity: 0.7 + result.similarity * 0.3,
                }}
              />
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm font-medium flex items-center gap-2">
                    <span className="flex h-6 w-6 items-center justify-center rounded-md bg-muted text-xs font-mono text-muted-foreground">{i + 1}</span>
                    <code className="text-xs">{result.citation}</code>
                  </CardTitle>
                  <div className="flex items-center gap-2">
                    {result.law_category && (
                      <Badge variant="secondary">{result.law_category}</Badge>
                    )}
                    <Badge
                      variant={
                        result.similarity > 0.6
                          ? "default"
                          : result.similarity > 0.4
                            ? "secondary"
                            : "outline"
                      }
                    >
                      {(result.similarity * 100).toFixed(1)}%
                    </Badge>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <p className="text-sm whitespace-pre-wrap line-clamp-6 text-muted-foreground">
                  {result.chunk_text}
                </p>
                {result.source_url && (
                  <a
                    href={result.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-primary hover:underline mt-2 block truncate"
                  >
                    {result.source_url}
                  </a>
                )}
                {result.tax_types && result.tax_types.length > 0 && (
                  <div className="flex gap-1 mt-3">
                    {result.tax_types.map((t) => (
                      <Badge key={t} variant="outline" className="text-xs">
                        {t}
                      </Badge>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
