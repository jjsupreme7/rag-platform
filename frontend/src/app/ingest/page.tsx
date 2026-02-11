"use client";

import { useState, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Upload } from "lucide-react";
import { uploadPDF } from "@/lib/api";
import { useProject } from "@/lib/project-context";

const CATEGORIES = [
  "Statute (RCW)",
  "Administrative Code (WAC)",
  "Excise Tax Advisory (ETA)",
  "Tax Determination (WTD)",
  "Special Notice",
  "Tax Topic",
  "Industry Guide",
  "Other",
];

export default function IngestPage() {
  const { activeProject } = useProject();
  const [file, setFile] = useState<File | null>(null);
  const [category, setCategory] = useState("Other");
  const [citation, setCitation] = useState("");
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<{
    status: string;
    title?: string;
    chunks_created?: number;
    document_id?: string | null;
    error?: string;
  } | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setResult(null);
    try {
      const res = await uploadPDF(file, category, citation || undefined, activeProject?.id);
      setResult(res);
      if (res.status === "success") {
        setFile(null);
        setCitation("");
        if (inputRef.current) inputRef.current.value = "";
      }
    } catch (e) {
      setResult({ status: "error", error: String(e) });
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="max-w-2xl">
      <h2 className="text-2xl font-bold tracking-tight mb-1">Ingest Documents</h2>
      <p className="text-sm text-muted-foreground mb-6">
        Upload a PDF to parse, chunk, embed, and store in your knowledge base.
      </p>

      <div className="space-y-5">
        {/* File input */}
        <div>
          <label className="text-sm font-medium mb-1.5 block">PDF File</label>
          <div className="rounded-xl border-2 border-dashed border-border hover:border-primary/40 transition-colors p-6 text-center">
            <Upload className="h-8 w-8 text-muted-foreground/40 mx-auto mb-2" />
            <Input
              ref={inputRef}
              type="file"
              accept=".pdf"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
              className="border-0 shadow-none px-0 text-center file:mr-3 file:rounded-lg file:border-0 file:bg-primary file:text-primary-foreground file:px-4 file:py-1.5 file:text-sm file:font-medium file:cursor-pointer hover:file:bg-primary/90"
            />
            {file && (
              <p className="text-xs text-muted-foreground mt-2">
                {file.name} ({(file.size / 1024).toFixed(0)} KB)
              </p>
            )}
          </div>
        </div>

        {/* Category select */}
        <div>
          <label className="text-sm font-medium mb-1.5 block">Category</label>
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="w-full rounded-lg border border-input bg-background px-3 py-2.5 text-sm cursor-pointer hover:border-primary/40 transition-colors focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50"
          >
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>

        {/* Citation */}
        <div>
          <label className="text-sm font-medium mb-1.5 block">
            Citation{" "}
            <span className="text-muted-foreground font-normal">
              (optional)
            </span>
          </label>
          <Input
            placeholder="e.g. RCW 82.08.02565, ETA 3217.2024"
            value={citation}
            onChange={(e) => setCitation(e.target.value)}
            className="focus-visible:ring-primary/30 focus-visible:border-primary/50"
          />
        </div>

        {/* Upload button */}
        <Button onClick={handleUpload} disabled={!file || uploading} size="lg">
          <Upload className="h-4 w-4 mr-2" />
          {uploading ? "Processing..." : "Upload & Process"}
        </Button>
      </div>

      {/* Result */}
      {result && (
        <div
          className={`mt-6 rounded-md border p-4 ${
            result.status === "success"
              ? "border-green-500/50 bg-green-50 dark:bg-green-950/20"
              : "border-red-500/50 bg-red-50 dark:bg-red-950/20"
          }`}
        >
          {result.status === "success" ? (
            <div className="space-y-1">
              <p className="font-medium text-green-700 dark:text-green-400">
                Document ingested successfully
              </p>
              <p className="text-sm">
                <strong>{result.title}</strong>
              </p>
              <p className="text-sm">
                <Badge variant="secondary">
                  {result.chunks_created} chunks created
                </Badge>
              </p>
            </div>
          ) : (
            <p className="text-sm text-red-700 dark:text-red-400">
              Error: {result.error}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
