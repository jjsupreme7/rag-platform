"use client";

import { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  FileText,
  Database,
  BookOpen,
  Building2,
  Upload,
  Search,
  MessageSquare,
  ArrowRight,
} from "lucide-react";
import { fetchStats } from "@/lib/api";
import { useProject } from "@/lib/project-context";
import Link from "next/link";

const STAT_CARDS = [
  {
    key: "knowledge_documents",
    label: "Documents",
    description: "Knowledge base docs",
    icon: FileText,
    color: "text-indigo-600",
    bg: "bg-indigo-50",
    border: "border-indigo-100",
  },
  {
    key: "tax_law_chunks",
    label: "Tax Law Chunks",
    description: "Embedded text chunks",
    icon: Database,
    color: "text-emerald-600",
    bg: "bg-emerald-50",
    border: "border-emerald-100",
  },
  {
    key: "rcw_chunks",
    label: "RCW Chunks",
    description: "Revised Code of WA",
    icon: BookOpen,
    color: "text-amber-600",
    bg: "bg-amber-50",
    border: "border-amber-100",
  },
  {
    key: "vendor_background_chunks",
    label: "Vendor Chunks",
    description: "Vendor background data",
    icon: Building2,
    color: "text-violet-600",
    bg: "bg-violet-50",
    border: "border-violet-100",
  },
];

const QUICK_ACTIONS = [
  {
    label: "Upload PDF",
    description: "Ingest a new document",
    href: "/ingest",
    icon: Upload,
  },
  {
    label: "Search",
    description: "Query your knowledge base",
    href: "/search",
    icon: Search,
  },
  {
    label: "Start Chat",
    description: "Ask questions with RAG",
    href: "/chat",
    icon: MessageSquare,
  },
];

export default function DashboardPage() {
  const { activeProject } = useProject();
  const [stats, setStats] = useState<Record<string, number | null>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetchStats(activeProject?.id)
      .then(setStats)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [activeProject?.id]);

  return (
    <div className="space-y-8">
      {/* Welcome section */}
      <div>
        <h2 className="text-2xl font-bold tracking-tight">
          {activeProject ? activeProject.name : "Dashboard"}
        </h2>
        <p className="text-muted-foreground mt-1">
          {activeProject?.description || "Overview of your knowledge base and quick actions."}
        </p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {STAT_CARDS.map(({ key, label, description, icon: Icon, color, bg, border }) => (
          <Card
            key={key}
            className={`relative overflow-hidden border ${border} transition-shadow hover:shadow-md`}
          >
            <CardContent className="p-5">
              <div className="flex items-start justify-between">
                <div className="space-y-1">
                  <p className="text-sm font-medium text-muted-foreground">{label}</p>
                  <p className="text-3xl font-bold tracking-tight">
                    {loading ? (
                      <span className="inline-block h-9 w-20 rounded bg-muted animate-pulse" />
                    ) : stats[key] != null ? (
                      stats[key]!.toLocaleString()
                    ) : (
                      <span className="text-lg text-muted-foreground/50">N/A</span>
                    )}
                  </p>
                  <p className="text-xs text-muted-foreground/70">{description}</p>
                </div>
                <div className={`flex h-10 w-10 items-center justify-center rounded-xl ${bg}`}>
                  <Icon className={`h-5 w-5 ${color}`} />
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Quick actions */}
      <div>
        <h3 className="text-sm font-medium text-muted-foreground mb-3">Quick Actions</h3>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {QUICK_ACTIONS.map(({ label, description, href, icon: Icon }) => (
            <Link key={href} href={href}>
              <Card className="group cursor-pointer transition-all hover:shadow-md hover:border-primary/30">
                <CardContent className="flex items-center gap-4 p-4">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary group-hover:bg-primary group-hover:text-primary-foreground transition-colors">
                    <Icon className="h-5 w-5" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium">{label}</p>
                    <p className="text-xs text-muted-foreground">{description}</p>
                  </div>
                  <ArrowRight className="h-4 w-4 text-muted-foreground/40 group-hover:text-primary transition-colors" />
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
