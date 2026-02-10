"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

export interface Project {
  id: string;
  name: string;
  description: string | null;
  system_prompt: string;
  chat_model: string;
  embedding_model: string;
  created_at: string;
}

interface ProjectContextValue {
  projects: Project[];
  activeProject: Project | null;
  setActiveProject: (p: Project) => void;
  refreshProjects: () => Promise<void>;
  loading: boolean;
}

const ProjectContext = createContext<ProjectContextValue>({
  projects: [],
  activeProject: null,
  setActiveProject: () => {},
  refreshProjects: async () => {},
  loading: true,
});

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";
const STORAGE_KEY = "rag-active-project-id";

export function ProjectProvider({ children }: { children: ReactNode }) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProject, setActiveProjectState] = useState<Project | null>(null);
  const [loading, setLoading] = useState(true);

  async function fetchProjects() {
    try {
      const res = await fetch(`${API_BASE}/api/projects`);
      if (!res.ok) return;
      const data: Project[] = await res.json();
      setProjects(data);
      return data;
    } catch {
      return undefined;
    }
  }

  async function refreshProjects() {
    await fetchProjects();
  }

  // Load projects on mount
  useEffect(() => {
    fetchProjects().then((data) => {
      if (!data || data.length === 0) {
        setLoading(false);
        return;
      }
      // Restore saved project or pick first
      const savedId = localStorage.getItem(STORAGE_KEY);
      const saved = savedId ? data.find((p) => p.id === savedId) : null;
      setActiveProjectState(saved || data[0]);
      setLoading(false);
    });
  }, []);

  function setActiveProject(p: Project) {
    setActiveProjectState(p);
    localStorage.setItem(STORAGE_KEY, p.id);
  }

  return (
    <ProjectContext.Provider
      value={{ projects, activeProject, setActiveProject, refreshProjects, loading }}
    >
      {children}
    </ProjectContext.Provider>
  );
}

export function useProject() {
  return useContext(ProjectContext);
}
