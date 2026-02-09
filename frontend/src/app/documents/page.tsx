"use client";

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { fetchDocuments, fetchCategories, type Document } from "@/lib/api";
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

  // Reset when project changes
  useEffect(() => {
    setPage(0);
    setSelectedCategory(null);
  }, [activeProject?.id]);

  // Load categories
  useEffect(() => {
    fetchCategories(activeProject?.id).then(setCategories).catch(console.error);
  }, [activeProject?.id]);

  // Load documents when page or category changes
  useEffect(() => {
    setLoading(true);
    fetchDocuments(page * PAGE_SIZE, PAGE_SIZE, selectedCategory || undefined, activeProject?.id)
      .then((r) => {
        setDocuments(r.documents);
        setTotal(r.total);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [page, selectedCategory, activeProject?.id]);

  const totalPages = Math.ceil(total / PAGE_SIZE);
  const allCount = Object.values(categories).reduce((a, b) => a + b, 0);
  const sortedCategories = Object.entries(categories).sort(
    ([, a], [, b]) => b - a
  );

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-2xl font-bold">Documents</h2>
          <p className="text-sm text-muted-foreground">
            {total.toLocaleString()} documents
            {selectedCategory ? ` in ${selectedCategory}` : " in knowledge base"}
          </p>
        </div>
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
                  <TableHead>Type</TableHead>
                  <TableHead className="text-right">Chunks</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {documents.map((doc) => (
                  <TableRow key={doc.id}>
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
                      <Badge variant="outline">{doc.document_type}</Badge>
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
    </div>
  );
}
