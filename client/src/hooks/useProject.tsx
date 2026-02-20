import { createContext, useContext, useState, useCallback, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/hooks/useAuth";
import type { Project } from "@shared/schema";

interface ProjectContextValue {
  projects: Project[];
  currentProject: Project | null;
  currentProjectId: string | null;
  selectProject: (projectId: string) => void;
  isLoading: boolean;
  isProjectLocked: boolean;
}

const ProjectContext = createContext<ProjectContextValue | null>(null);

const STORAGE_KEY = "defuse_selected_project_id";

export function ProjectProvider({ children }: { children: React.ReactNode }) {
  const { user, isAdmin } = useAuth();

  const [selectedId, setSelectedId] = useState<string | null>(() => {
    return localStorage.getItem(STORAGE_KEY);
  });

  const { data: projects = [], isLoading } = useQuery<Project[]>({
    queryKey: ["/api/projects"],
    enabled: !!user,
  });

  const isProjectLocked = !isAdmin && !!user?.projectId;

  const selectProject = useCallback((projectId: string) => {
    if (isProjectLocked) return;
    setSelectedId(projectId);
    localStorage.setItem(STORAGE_KEY, projectId);
  }, [isProjectLocked]);

  useEffect(() => {
    if (user && !isAdmin && user.projectId) {
      setSelectedId(user.projectId);
      localStorage.setItem(STORAGE_KEY, user.projectId);
    }
  }, [user, isAdmin]);

  useEffect(() => {
    if (!isLoading && projects.length > 0 && !selectedId && isAdmin) {
      setSelectedId(projects[0].id);
      localStorage.setItem(STORAGE_KEY, projects[0].id);
    }
  }, [isLoading, projects, selectedId, isAdmin]);

  const currentProject = projects.find(p => p.id === selectedId) || null;

  return (
    <ProjectContext.Provider value={{
      projects,
      currentProject,
      currentProjectId: selectedId,
      selectProject,
      isLoading,
      isProjectLocked,
    }}>
      {children}
    </ProjectContext.Provider>
  );
}

export function useProject(): ProjectContextValue {
  const ctx = useContext(ProjectContext);
  if (!ctx) {
    throw new Error("useProject must be used within a ProjectProvider");
  }
  return ctx;
}
