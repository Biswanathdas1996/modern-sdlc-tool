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

export function ProjectProvider({ children }: { children: React.ReactNode }) {
  const { user, isAdmin } = useAuth();

  const [selectedId, setSelectedId] = useState<string | null>(null);

  const { data: projects = [], isLoading } = useQuery<Project[]>({
    queryKey: ["/api/user-projects"],
    enabled: !!user,
  });

  const isProjectLocked = !isAdmin && (user?.projectIds?.length === 1);

  const selectProject = useCallback((projectId: string) => {
    if (isProjectLocked) return;
    setSelectedId(projectId);
  }, [isProjectLocked]);

  useEffect(() => {
    if (user && !isAdmin && user.projectIds?.length === 1) {
      setSelectedId(user.projectIds[0]);
    }
  }, [user, isAdmin]);

  useEffect(() => {
    if (!isLoading && projects.length > 0 && !selectedId) {
      setSelectedId(projects[0].id);
    }
  }, [isLoading, projects, selectedId]);

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
