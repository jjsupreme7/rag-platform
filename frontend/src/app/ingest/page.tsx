"use client";

import { useState, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { uploadPDF } from "@/lib/api";

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
      const res = await uploadPDF(file, category, citation || undefined);
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
      <h2 className="text-2xl font-bold mb-1">Ingest Documents</h2>
      <p className="text-sm text-muted-foreground mb-6">
        Upload a PDF to parse, chunk, embed, and store in your knowledge base.
      </p>

      <div className="space-y-4">
        {/* File input */}
        <div>
          <label className="text-sm font-medium mb-1 block">PDF File</label>
          <Input
            ref={inputRef}
            type="file"
            accept=".pdf"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
          />
          {file && (
            <p className="text-xs text-muted-foreground mt-1">
              {file.name} ({(file.size / 1024).toFixed(0)} KB)
            </p>
          )}
        </div>

        {/* Category select */}
        <div>
          <label className="text-sm font-medium mb-1 block">Category</label>
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
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
          <label className="text-sm font-medium mb-1 block">
            Citation{" "}
            <span className="text-muted-foreground font-normal">
              (optional)
            </span>
          </label>
          <Input
            placeholder="e.g. RCW 82.08.02565, ETA 3217.2024"
            value={citation}
            onChange={(e) => setCitation(e.target.value)}
          />
        </div>

        {/* Upload button */}
        <Button onClick={handleUpload} disabled={!file || uploading}>
          {uploading ? "Uploading..." : "Upload & Process"}
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
