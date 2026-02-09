"use client";

import {
  LayoutDashboard,
  FileText,
  Upload,
  MessageSquare,
  Search,
  Settings,
  ChevronsUpDown,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import {
  Sidebar,
  SidebarContent,
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
  { title: "Search", href: "/search", icon: Search },
  { title: "Chat", href: "/chat", icon: MessageSquare },
  { title: "Settings", href: "/settings", icon: Settings },
];

export function AppSidebar() {
  const pathname = usePathname();
  const { projects, activeProject, setActiveProject, loading } = useProject();

  return (
    <Sidebar>
      <SidebarHeader className="border-b px-4 py-3">
        <label className="text-xs font-medium text-muted-foreground mb-1 block">
          Project
        </label>
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
              className="w-full appearance-none rounded-md border border-input bg-background px-3 py-2 pr-8 text-sm font-medium cursor-pointer hover:bg-accent transition-colors"
            >
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
            <ChevronsUpDown className="absolute right-2 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
          </div>
        )}
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Navigation</SidebarGroupLabel>
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
    </Sidebar>
  );
}
