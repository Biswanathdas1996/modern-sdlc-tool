import { createContext, useContext, useState, useCallback, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import type { Project } from "@shared/schema";

interface ProjectContextValue {
  projects: Project[];
  currentProject: Project | null;
  currentProjectId: string | null;
  selectProject: (projectId: string) => void;
  isLoading: boolean;
}

const ProjectContext = createContext<ProjectContextValue | null>(null);

const STORAGE_KEY = "defuse_selected_project_id";

export function ProjectProvider({ children }: { children: React.ReactNode }) {
  const [selectedId, setSelectedId] = useState<string | null>(() => {
    return localStorage.getItem(STORAGE_KEY);
  });

  const { data: projects = [], isLoading } = useQuery<Project[]>({
    queryKey: ["/api/projects"],
  });

  const selectProject = useCallback((projectId: string) => {
    setSelectedId(projectId);
    localStorage.setItem(STORAGE_KEY, projectId);
  }, []);

  const currentProject = projects.find(p => p.id === selectedId) || null;

  useEffect(() => {
    if (!isLoading && projects.length > 0 && !currentProject) {
      selectProject(projects[0].id);
    }
  }, [isLoading, projects, currentProject, selectProject]);

  return (
    <ProjectContext.Provider value={{
      projects,
      currentProject,
      currentProjectId: currentProject?.id || null,
      selectProject,
      isLoading,
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
