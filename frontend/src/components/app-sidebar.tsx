"use client";

import {
  LayoutDashboard,
  FileText,
  Upload,
  Globe,
  Radar,
  MessageSquare,
  Search,
  Settings,
  ChevronsUpDown,
  Database,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
import { useProject } from "@/lib/project-context";

const navItems = [
  { title: "Dashboard", href: "/", icon: LayoutDashboard },
  { title: "Documents", href: "/documents", icon: FileText },
  { title: "Ingest", href: "/ingest", icon: Upload },
  { title: "Scrape", href: "/scrape", icon: Globe },
  { title: "Monitor", href: "/monitor", icon: Radar },
  { title: "Search", href: "/search", icon: Search },
  { title: "Chat", href: "/chat", icon: MessageSquare },
  { title: "Settings", href: "/settings", icon: Settings },
];

export function AppSidebar() {
  const pathname = usePathname();
  const { projects, activeProject, setActiveProject, loading } = useProject();

  return (
    <Sidebar>
      <SidebarHeader className="border-b px-4 py-4">
        <div className="flex items-center gap-2.5 mb-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <Database className="h-4 w-4" />
          </div>
          <div>
            <h2 className="text-sm font-semibold tracking-tight">RAG Platform</h2>
            <p className="text-[11px] text-muted-foreground">Knowledge Base</p>
          </div>
        </div>
        {loading ? (
          <div className="h-9 rounded-md bg-muted animate-pulse" />
        ) : (
          <div className="relative">
            <select
              value={activeProject?.id || ""}
              onChange={(e) => {
                const p = projects.find((p) => p.id === e.target.value);
                if (p) setActiveProject(p);
              }}
              className="w-full appearance-none rounded-lg border border-input bg-background px-3 py-2 pr-8 text-sm font-medium cursor-pointer hover:border-primary/50 transition-colors focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50"
            >
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
            <ChevronsUpDown className="absolute right-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
          </div>
        )}
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel className="text-[11px] uppercase tracking-wider font-medium text-muted-foreground/70">
            Navigation
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {navItems.map((item) => (
                <SidebarMenuItem key={item.href}>
                  <SidebarMenuButton asChild isActive={pathname === item.href}>
                    <Link href={item.href}>
                      <item.icon />
                      <span>{item.title}</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter className="border-t px-4 py-3">
        <p className="text-[11px] text-muted-foreground/50">
          RAG Platform v0.3.0
        </p>
      </SidebarFooter>
    </Sidebar>
  );
}
