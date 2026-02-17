"use client";

import { useEffect, useState } from "react";
import {
  FileText,
  Database,
  Globe,
  MessageSquare,
  ArrowRight,
  Upload,
  Search,
  Clock,
  Layers,
  Activity,
  Zap,
} from "lucide-react";
import {
  fetchStats,
  fetchCategories,
  fetchSourceTypes,
  fetchRecentChats,
  type RecentChat,
} from "@/lib/api";
import { useProject } from "@/lib/project-context";
import Link from "next/link";
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
} from "recharts";

// ---------------------------------------------------------------------------
// Stat cards config
// ---------------------------------------------------------------------------

const STAT_CARDS = [
  {
    key: "knowledge_documents",
    label: "DOCUMENTS",
    description: "Knowledge base",
    icon: FileText,
    gradient: "from-indigo-500/20 to-indigo-500/5",
    iconBg: "bg-indigo-500/20",
    iconColor: "text-indigo-400",
    borderGlow: "hover:shadow-indigo-500/10",
  },
  {
    key: "tax_law_chunks",
    label: "CHUNKS",
    description: "Embedded vectors",
    icon: Database,
    gradient: "from-emerald-500/20 to-emerald-500/5",
    iconBg: "bg-emerald-500/20",
    iconColor: "text-emerald-400",
    borderGlow: "hover:shadow-emerald-500/10",
  },
  {
    key: "scraped",
    label: "SCRAPED",
    description: "From website",
    icon: Globe,
    gradient: "from-cyan-500/20 to-cyan-500/5",
    iconBg: "bg-cyan-500/20",
    iconColor: "text-cyan-400",
    borderGlow: "hover:shadow-cyan-500/10",
  },
  {
    key: "categories",
    label: "CATEGORIES",
    description: "Source types",
    icon: Layers,
    gradient: "from-amber-500/20 to-amber-500/5",
    iconBg: "bg-amber-500/20",
    iconColor: "text-amber-400",
    borderGlow: "hover:shadow-amber-500/10",
  },
];

const QUICK_ACTIONS = [
  { label: "Upload PDF", description: "Ingest a new document", href: "/ingest", icon: Upload },
  { label: "Search KB", description: "Query knowledge base", href: "/search", icon: Search },
  { label: "Start Chat", description: "Ask questions with RAG", href: "/chat", icon: MessageSquare },
];

// Chart colors — teal-dominant palette for dark metallic look
const CHART_COLORS = [
  "#2dd4bf",
  "#818cf8",
  "#f59e0b",
  "#f472b6",
  "#34d399",
  "#a78bfa",
  "#fb923c",
  "#f87171",
  "#38bdf8",
  "#c084fc",
];

const PIE_COLORS = ["#818cf8", "#2dd4bf"];

export default function DashboardPage() {
  const { activeProject } = useProject();
  const [stats, setStats] = useState<Record<string, number | null>>({});
  const [categories, setCategories] = useState<Record<string, number>>({});
  const [sourceTypes, setSourceTypes] = useState<Record<string, number>>({});
  const [recentChats, setRecentChats] = useState<RecentChat[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    const pid = activeProject?.id;
    Promise.all([
      fetchStats(pid).catch(() => ({})),
      fetchCategories(pid).catch(() => ({})),
      fetchSourceTypes(pid).catch(() => ({})),
      fetchRecentChats(5, pid).catch(() => []),
    ]).then(([s, c, st, rc]) => {
      setStats(s);
      setCategories(c);
      setSourceTypes(st);
      setRecentChats(rc as RecentChat[]);
      setLoading(false);
    });
  }, [activeProject?.id]);

  const scrapedCount = sourceTypes["web_scrape"] || 0;
  const categoryCount = Object.keys(categories).length;

  // Chart data
  const catData = Object.entries(categories)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8)
    .map(([name, value]) => ({ name: name.length > 20 ? name.slice(0, 18) + "…" : name, value }));

  const sourceData = Object.entries(sourceTypes).map(([name, value]) => ({
    name: name === "web_scrape" ? "Scraped" : name === "upload" ? "Uploaded" : name,
    value,
  }));

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">
            {activeProject ? activeProject.name : "Overview"}
          </h2>
          <p className="text-sm text-muted-foreground mt-0.5">
            {activeProject?.description || "Knowledge base overview and activity."}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5 rounded-full bg-emerald-500/10 px-3 py-1">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
            </span>
            <span className="text-xs font-medium text-emerald-400">System Online</span>
          </div>
        </div>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {STAT_CARDS.map(({ key, label, description, icon: Icon, gradient, iconBg, iconColor, borderGlow }) => {
          let value: number | null = null;
          if (key === "scraped") value = scrapedCount;
          else if (key === "categories") value = categoryCount;
          else value = stats[key] ?? null;

          return (
            <div
              key={key}
              className={`group relative overflow-hidden rounded-xl border border-white/[0.06] bg-card p-5 transition-all duration-300 hover:shadow-xl ${borderGlow} hover:border-white/[0.12]`}
            >
              {/* Gradient overlay */}
              <div className={`absolute inset-0 bg-gradient-to-br ${gradient} opacity-0 group-hover:opacity-100 transition-opacity duration-300`} />
              <div className="relative flex items-start justify-between">
                <div>
                  <p className="text-[11px] font-semibold tracking-[0.2em] text-muted-foreground">
                    {label}
                  </p>
                  <p className="text-4xl font-bold tracking-tight mt-2">
                    {loading ? (
                      <span className="inline-block h-10 w-24 rounded-lg bg-white/[0.04] animate-pulse" />
                    ) : value != null ? (
                      value.toLocaleString()
                    ) : (
                      <span className="text-lg text-muted-foreground/50">N/A</span>
                    )}
                  </p>
                  <p className="text-xs text-muted-foreground/70 mt-1.5">{description}</p>
                </div>
                <div className={`flex h-11 w-11 items-center justify-center rounded-xl ${iconBg}`}>
                  <Icon className={`h-5 w-5 ${iconColor}`} />
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Category breakdown - bar chart */}
        <div className="lg:col-span-2 rounded-xl border border-white/[0.06] bg-card p-5">
          <div className="flex items-center gap-2 mb-5">
            <Activity className="h-4 w-4 text-primary" />
            <h3 className="text-sm font-semibold tracking-widest text-muted-foreground">
              DOCUMENTS BY CATEGORY
            </h3>
          </div>
          {loading ? (
            <div className="h-64 rounded-lg bg-white/[0.03] animate-pulse" />
          ) : catData.length > 0 ? (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={catData} layout="vertical" margin={{ left: 8, right: 16, top: 4, bottom: 4 }}>
                <XAxis
                  type="number"
                  tick={{ fontSize: 11, fill: "#737373" }}
                  axisLine={{ stroke: "rgba(255,255,255,0.06)" }}
                  tickLine={false}
                />
                <YAxis
                  type="category"
                  dataKey="name"
                  width={140}
                  tick={{ fontSize: 11, fill: "#a3a3a3" }}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "rgba(20, 20, 30, 0.95)",
                    border: "1px solid rgba(255,255,255,0.1)",
                    borderRadius: 10,
                    fontSize: 12,
                    color: "#e5e5e5",
                    boxShadow: "0 8px 32px rgba(0,0,0,0.4)",
                  }}
                />
                <Bar dataKey="value" radius={[0, 6, 6, 0]}>
                  {catData.map((_, i) => (
                    <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-sm text-muted-foreground">No data</p>
          )}
        </div>

        {/* Source breakdown - pie chart */}
        <div className="rounded-xl border border-white/[0.06] bg-card p-5">
          <div className="flex items-center gap-2 mb-5">
            <Zap className="h-4 w-4 text-primary" />
            <h3 className="text-sm font-semibold tracking-widest text-muted-foreground">
              SOURCE BREAKDOWN
            </h3>
          </div>
          {loading ? (
            <div className="h-64 rounded-lg bg-white/[0.03] animate-pulse" />
          ) : sourceData.length > 0 ? (
            <div className="flex flex-col items-center">
              <ResponsiveContainer width="100%" height={180}>
                <PieChart>
                  <Pie
                    data={sourceData}
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={80}
                    paddingAngle={4}
                    dataKey="value"
                    strokeWidth={0}
                  >
                    {sourceData.map((_, i) => (
                      <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "rgba(20, 20, 30, 0.95)",
                      border: "1px solid rgba(255,255,255,0.1)",
                      borderRadius: 10,
                      fontSize: 12,
                      color: "#e5e5e5",
                      boxShadow: "0 8px 32px rgba(0,0,0,0.4)",
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
              <div className="flex gap-5 mt-3">
                {sourceData.map((entry, i) => (
                  <div key={entry.name} className="flex items-center gap-2 text-xs">
                    <span
                      className="inline-block h-3 w-3 rounded-md"
                      style={{ backgroundColor: PIE_COLORS[i % PIE_COLORS.length] }}
                    />
                    <span className="text-muted-foreground">{entry.name}</span>
                    <span className="font-bold text-foreground">{entry.value.toLocaleString()}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">No data</p>
          )}
        </div>
      </div>

      {/* Bottom row: Recent Activity + Quick Actions */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Recent activity */}
        <div className="lg:col-span-2 rounded-xl border border-white/[0.06] bg-card p-5">
          <div className="flex items-center gap-2 mb-5">
            <Clock className="h-4 w-4 text-primary" />
            <h3 className="text-sm font-semibold tracking-widest text-muted-foreground">
              RECENT ACTIVITY
            </h3>
          </div>
          {loading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-14 rounded-lg bg-white/[0.03] animate-pulse" />
              ))}
            </div>
          ) : recentChats.length > 0 ? (
            <div className="space-y-2">
              {recentChats.map((chat) => (
                <div
                  key={chat.id}
                  className="flex items-center gap-3 rounded-lg border border-white/[0.04] bg-white/[0.02] p-3.5 transition-all hover:bg-white/[0.04] hover:border-white/[0.08]"
                >
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/15">
                    <MessageSquare className="h-4 w-4 text-primary" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">
                      {chat.question}
                    </p>
                    <div className="flex items-center gap-3 mt-1">
                      <span className="text-[11px] text-muted-foreground flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        {chat.response_time_ms ? `${(chat.response_time_ms / 1000).toFixed(1)}s` : "—"}
                      </span>
                      {chat.sources_count != null && (
                        <span className="text-[11px] text-muted-foreground">
                          {chat.sources_count} sources
                        </span>
                      )}
                    </div>
                  </div>
                  <span className="text-[11px] text-muted-foreground/50 shrink-0 font-mono">
                    {new Date(chat.created_at).toLocaleDateString()}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-8 text-muted-foreground/50">
              <MessageSquare className="h-8 w-8 mb-2" />
              <p className="text-sm">No recent chat activity.</p>
            </div>
          )}
        </div>

        {/* Quick actions */}
        <div className="rounded-xl border border-white/[0.06] bg-card p-5">
          <div className="flex items-center gap-2 mb-5">
            <Zap className="h-4 w-4 text-primary" />
            <h3 className="text-sm font-semibold tracking-widest text-muted-foreground">
              QUICK ACTIONS
            </h3>
          </div>
          <div className="space-y-2.5">
            {QUICK_ACTIONS.map(({ label, description, href, icon: Icon }) => (
              <Link key={href} href={href}>
                <div className="group flex items-center gap-3 rounded-lg border border-white/[0.04] bg-white/[0.02] p-3.5 transition-all hover:bg-primary/10 hover:border-primary/30 cursor-pointer">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/15 text-primary group-hover:bg-primary group-hover:text-primary-foreground transition-all duration-200 group-hover:shadow-lg group-hover:shadow-primary/20">
                    <Icon className="h-4.5 w-4.5" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold">{label}</p>
                    <p className="text-[11px] text-muted-foreground/70">{description}</p>
                  </div>
                  <ArrowRight className="h-4 w-4 text-muted-foreground/30 group-hover:text-primary group-hover:translate-x-0.5 transition-all" />
                </div>
              </Link>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
