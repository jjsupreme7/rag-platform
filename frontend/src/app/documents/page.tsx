"use client";

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { fetchDocuments, fetchCategories, fetchDocument, type Document, type Chunk } from "@/lib/api";
import { useProject } from "@/lib/project-context";

const PAGE_SIZE = 25;

export default function DocumentsPage() {
  const { activeProject } = useProject();
  const [documents, setDocuments] = useState<Document[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const [categories, setCategories] = useState<Record<string, number>>({});
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [selectedSourceType, setSelectedSourceType] = useState<string | null>(null);
  const [selectedDoc, setSelectedDoc] = useState<Document | null>(null);
  const [chunks, setChunks] = useState<Chunk[]>([]);
  const [chunksLoading, setChunksLoading] = useState(false);

  // Reset when project changes
  useEffect(() => {
    setPage(0);
    setSelectedCategory(null);
    setSelectedSourceType(null);
  }, [activeProject?.id]);

  // Load categories
  useEffect(() => {
    fetchCategories(activeProject?.id).then(setCategories).catch(console.error);
  }, [activeProject?.id]);

  // Load documents when page, category, or source type changes
  useEffect(() => {
    setLoading(true);
    fetchDocuments(page * PAGE_SIZE, PAGE_SIZE, selectedCategory || undefined, activeProject?.id, selectedSourceType || undefined)
      .then((r) => {
        setDocuments(r.documents);
        setTotal(r.total);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [page, selectedCategory, selectedSourceType, activeProject?.id]);

  function handleRowClick(doc: Document) {
    setSelectedDoc(doc);
    setChunks([]);
    setChunksLoading(true);
    fetchDocument(doc.id)
      .then((r) => setChunks(r.chunks))
      .catch(console.error)
      .finally(() => setChunksLoading(false));
  }

  const totalPages = Math.ceil(total / PAGE_SIZE);
  const allCount = Object.values(categories).reduce((a, b) => a + b, 0);
  const sortedCategories = Object.entries(categories).sort(
    ([, a], [, b]) => b - a
  );

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Documents</h2>
          <p className="text-sm text-muted-foreground">
            {total.toLocaleString()} documents
            {selectedCategory ? ` in ${selectedCategory}` : " in knowledge base"}
          </p>
        </div>
      </div>

      {/* Source type filter */}
      <div className="flex gap-2 mb-3">
        {[
          { key: null, label: "All Sources" },
          { key: "upload", label: "Uploaded" },
          { key: "web_scrape", label: "Web Scraped" },
        ].map(({ key, label }) => (
          <button
            key={label}
            onClick={() => {
              setSelectedSourceType(key);
              setPage(0);
            }}
            className={`px-3 py-1 rounded-full text-sm border transition-colors ${
              selectedSourceType === key
                ? "bg-primary text-primary-foreground border-primary"
                : "bg-background border-border hover:bg-accent"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Category filter tabs */}
      <div className="flex flex-wrap gap-2 mb-4">
        <button
          onClick={() => {
            setSelectedCategory(null);
            setPage(0);
          }}
          className={`px-3 py-1 rounded-full text-sm border transition-colors ${
            selectedCategory === null
              ? "bg-primary text-primary-foreground border-primary"
              : "bg-background border-border hover:bg-accent"
          }`}
        >
          All ({allCount.toLocaleString()})
        </button>
        {sortedCategories.map(([cat, count]) => (
          <button
            key={cat}
            onClick={() => {
              setSelectedCategory(cat);
              setPage(0);
            }}
            className={`px-3 py-1 rounded-full text-sm border transition-colors ${
              selectedCategory === cat
                ? "bg-primary text-primary-foreground border-primary"
                : "bg-background border-border hover:bg-accent"
            }`}
          >
            {cat} ({count.toLocaleString()})
          </button>
        ))}
      </div>

      {loading ? (
        <p className="text-muted-foreground">Loading...</p>
      ) : (
        <>
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Title</TableHead>
                  <TableHead>Citation</TableHead>
                  <TableHead>Category</TableHead>
                  <TableHead>Source</TableHead>
                  <TableHead className="text-right">Chunks</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {documents.map((doc) => (
                  <TableRow
                    key={doc.id}
                    className="cursor-pointer hover:bg-muted/50"
                    onClick={() => handleRowClick(doc)}
                  >
                    <TableCell className="font-medium max-w-[300px] truncate">
                      {doc.title || doc.source_file}
                    </TableCell>
                    <TableCell>
                      <code className="text-xs">{doc.citation}</code>
                    </TableCell>
                    <TableCell>
                      {doc.law_category && (
                        <Badge variant="secondary">{doc.law_category}</Badge>
                      )}
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={doc.source_type === "web_scrape" ? "default" : "outline"}
                        className={doc.source_type === "web_scrape" ? "bg-emerald-600" : ""}
                      >
                        {doc.source_type === "web_scrape" ? "Web" : "Upload"}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      {doc.total_chunks}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          <div className="flex items-center justify-between mt-4">
            <p className="text-sm text-muted-foreground">
              Page {page + 1} of {totalPages}
            </p>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0}
              >
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => p + 1)}
                disabled={page >= totalPages - 1}
              >
                Next
              </Button>
            </div>
          </div>
        </>
      )}
      <Sheet open={!!selectedDoc} onOpenChange={(open) => !open && setSelectedDoc(null)}>
        <SheetContent side="right" className="sm:max-w-2xl overflow-y-auto">
          {selectedDoc && (
            <>
              <SheetHeader>
                <SheetTitle className="text-lg pr-8">
                  {selectedDoc.title || selectedDoc.source_file}
                </SheetTitle>
                <SheetDescription asChild>
                  <div className="space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <code className="text-xs">{selectedDoc.citation}</code>
                      {selectedDoc.law_category && (
                        <Badge variant="secondary">{selectedDoc.law_category}</Badge>
                      )}
                      <Badge
                        variant={selectedDoc.source_type === "web_scrape" ? "default" : "outline"}
                        className={selectedDoc.source_type === "web_scrape" ? "bg-emerald-600" : ""}
                      >
                        {selectedDoc.source_type === "web_scrape" ? "Web Scraped" : "Uploaded"}
                      </Badge>
                      <span className="text-xs">
                        {selectedDoc.total_chunks} chunk{selectedDoc.total_chunks !== 1 ? "s" : ""}
                      </span>
                    </div>
                    {selectedDoc.source_url && (
                      <a
                        href={selectedDoc.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-primary hover:underline block truncate"
                      >
                        {selectedDoc.source_url}
                      </a>
                    )}
                  </div>
                </SheetDescription>
              </SheetHeader>

              <div className="px-4 pb-6 space-y-3">
                {chunksLoading ? (
                  <p className="text-sm text-muted-foreground">Loading chunks...</p>
                ) : chunks.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No chunks found.</p>
                ) : (
                  chunks.map((chunk) => (
                    <Card key={chunk.id}>
                      <CardContent className="p-4">
                        <div className="flex items-center gap-2 mb-2">
                          <span className="flex h-6 w-6 items-center justify-center rounded-md bg-muted text-xs font-mono text-muted-foreground shrink-0">
                            {chunk.chunk_number}
                          </span>
                          {chunk.section_title && (
                            <span className="text-sm font-medium truncate">
                              {chunk.section_title}
                            </span>
                          )}
                        </div>
                        <p className="text-sm whitespace-pre-wrap text-muted-foreground leading-relaxed">
                          {chunk.chunk_text}
                        </p>
                      </CardContent>
                    </Card>
                  ))
                )}
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}
