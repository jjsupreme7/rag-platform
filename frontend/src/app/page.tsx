"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FileText, Database, BookOpen, Building2 } from "lucide-react";
import { fetchStats } from "@/lib/api";

const STAT_CARDS = [
  { key: "knowledge_documents", label: "Documents", icon: FileText },
  { key: "tax_law_chunks", label: "Tax Law Chunks", icon: Database },
  { key: "rcw_chunks", label: "RCW Chunks", icon: BookOpen },
  { key: "vendor_background_chunks", label: "Vendor Chunks", icon: Building2 },
];

export default function DashboardPage() {
  const [stats, setStats] = useState<Record<string, number | null>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchStats()
      .then(setStats)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">Dashboard</h2>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {STAT_CARDS.map(({ key, label, icon: Icon }) => (
          <Card key={key}>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium">{label}</CardTitle>
              <Icon className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">
                {loading
                  ? "..."
                  : stats[key] != null
                    ? stats[key]!.toLocaleString()
                    : "N/A"}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
