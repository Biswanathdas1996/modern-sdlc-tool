import { useState, useEffect } from "react";
import { useLocation } from "wouter";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { GitBranch, Search, ArrowRight, ExternalLink, Folder, FileCode, Clock, Star, GitFork, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { WorkflowHeader } from "@/components/WorkflowHeader";
import { LoadingOverlay, LoadingSpinner } from "@/components/LoadingSpinner";
import { EmptyState } from "@/components/EmptyState";
import { apiRequest } from "@/lib/queryClient";
import { useSession } from "@/hooks/useSession";
import type { Project } from "@shared/schema";

const workflowSteps = [
  { id: "analyze", label: "Analyze", completed: false, active: true },
  { id: "document", label: "Document", completed: false, active: false },
  { id: "requirements", label: "Requirements", completed: false, active: false },
  { id: "brd", label: "BRD", completed: false, active: false },
  { id: "user-stories", label: "Stories", completed: false, active: false },
  { id: "test-cases", label: "Tests", completed: false, active: false },
  { id: "test-data", label: "Data", completed: false, active: false },
];

export default function AnalyzePage() {
  const [repoUrl, setRepoUrl] = useState("");
  const [analyzingProjectId, setAnalyzingProjectId] = useState<string | null>(null);
  const [, navigate] = useLocation();
  const queryClient = useQueryClient();
  const { saveSessionArtifact } = useSession();

  // Poll for projects to check status
  const { data: projects, isLoading: projectsLoading } = useQuery<Project[]>({
    queryKey: ["/api/projects"],
    refetchInterval: analyzingProjectId ? 2000 : false, // Poll every 2s when analyzing
  });

  // Check if analyzing project is complete
  useEffect(() => {
    if (analyzingProjectId && projects) {
      const project = projects.find(p => p.id === analyzingProjectId);
      if (project && project.status === "completed") {
        saveSessionArtifact("project", project);
        setAnalyzingProjectId(null);
        queryClient.invalidateQueries({ queryKey: ["/api/analysis/current"] });
        queryClient.invalidateQueries({ queryKey: ["/api/documentation/current"] });
        navigate("/documentation");
      } else if (project && project.status === "error") {
        setAnalyzingProjectId(null);
      }
    }
  }, [projects, analyzingProjectId, navigate, queryClient, saveSessionArtifact]);

  const analyzeMutation = useMutation({
    mutationFn: async (url: string) => {
      const response = await apiRequest("POST", "/api/projects/analyze", { repoUrl: url });
      return response.json();
    },
    onSuccess: (data: Project) => {
      queryClient.invalidateQueries({ queryKey: ["/api/projects"] });
      setAnalyzingProjectId(data.id); // Start polling for this project
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      await apiRequest("DELETE", `/api/projects/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/projects"] });
      queryClient.invalidateQueries({ queryKey: ["/api/documentation/current"] });
      queryClient.invalidateQueries({ queryKey: ["/api/analysis/current"] });
    },
  });

  const isAnalyzing = analyzeMutation.isPending || !!analyzingProjectId;
  const analyzingProject = projects?.find(p => p.id === analyzingProjectId);

  const handleAnalyze = () => {
    if (repoUrl.trim()) {
      analyzeMutation.mutate(repoUrl.trim());
    }
  };

  const handleDelete = (e: React.MouseEvent, projectId: string) => {
    e.stopPropagation();
    if (confirm("Are you sure you want to delete this project?")) {
      deleteMutation.mutate(projectId);
    }
  };

  const selectProject = (project: Project) => {
    saveSessionArtifact("project", project);
    queryClient.setQueryData(["currentProject"], project);
    navigate("/documentation");
  };

  const isValidGitHubUrl = (url: string) => {
    return url.match(/^https?:\/\/(www\.)?github\.com\/[\w-]+\/[\w.-]+\/?$/i);
  };

  return (
    <div className="flex flex-col h-full">
      {isAnalyzing && (
        <LoadingOverlay 
          message="Analyzing Repository..." 
          subMessage={analyzingProject 
            ? `Status: ${analyzingProject.status} - Fetching files, analyzing code, and generating documentation...`
            : "Extracting code structure, features, and tech stack"
          }
        />
      )}

      <WorkflowHeader
        steps={workflowSteps}
        title="Analyze GitHub Repository"
        description="Connect to a public GitHub repository to analyze its codebase and generate comprehensive documentation."
      />

      <div className="flex-1 overflow-auto p-6">
        <div className="max-w-4xl mx-auto space-y-8">
          <Card className="border-2 border-dashed border-primary/30 bg-primary/5">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <GitBranch className="h-5 w-5 text-primary" />
                Connect Repository
              </CardTitle>
              <CardDescription>
                Enter a public GitHub repository URL to begin analysis
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex gap-3">
                <div className="relative flex-1">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    type="url"
                    placeholder="https://github.com/owner/repository"
                    value={repoUrl}
                    onChange={(e) => setRepoUrl(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleAnalyze()}
                    className="pl-10"
                    data-testid="input-repo-url"
                  />
                </div>
                <Button
                  onClick={handleAnalyze}
                  disabled={!isValidGitHubUrl(repoUrl) || isAnalyzing}
                  data-testid="button-analyze"
                >
                  {isAnalyzing ? (
                    <LoadingSpinner size="sm" />
                  ) : (
                    <>
                      Analyze
                      <ArrowRight className="ml-2 h-4 w-4" />
                    </>
                  )}
                </Button>
              </div>
              {repoUrl && !isValidGitHubUrl(repoUrl) && (
                <p className="text-sm text-destructive mt-2">
                  Please enter a valid GitHub repository URL (e.g., https://github.com/owner/repo)
                </p>
              )}
              {analyzeMutation.isError && (
                <p className="text-sm text-destructive mt-2">
                  Failed to analyze repository. Please check the URL and try again.
                </p>
              )}
            </CardContent>
          </Card>

          <div className="grid md:grid-cols-3 gap-4">
            <Card className="bg-card">
              <CardContent className="pt-6">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-md bg-primary/10">
                    <FileCode className="h-5 w-5 text-primary" />
                  </div>
                  <div>
                    <p className="text-2xl font-bold text-foreground">AI-Powered</p>
                    <p className="text-sm text-muted-foreground">Code Analysis</p>
                  </div>
                </div>
              </CardContent>
            </Card>
            <Card className="bg-card">
              <CardContent className="pt-6">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-md bg-success/10">
                    <Folder className="h-5 w-5 text-success" />
                  </div>
                  <div>
                    <p className="text-2xl font-bold text-foreground">Full Stack</p>
                    <p className="text-sm text-muted-foreground">Detection</p>
                  </div>
                </div>
              </CardContent>
            </Card>
            <Card className="bg-card">
              <CardContent className="pt-6">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-md bg-accent/10">
                    <Clock className="h-5 w-5 text-accent" />
                  </div>
                  <div>
                    <p className="text-2xl font-bold text-foreground">Fast</p>
                    <p className="text-sm text-muted-foreground">Generation</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          <div>
            <h2 className="text-lg font-semibold text-foreground mb-4">Recent Projects</h2>
            {projectsLoading ? (
              <div className="flex justify-center py-8">
                <LoadingSpinner text="Loading projects..." />
              </div>
            ) : projects && projects.length > 0 ? (
              <ScrollArea className="h-[300px]">
                <div className="space-y-3">
                  {projects.map((project) => (
                    <Card
                      key={project.id}
                      className="hover-elevate cursor-pointer transition-colors"
                      onClick={() => selectProject(project)}
                      data-testid={`card-project-${project.id}`}
                    >
                      <CardContent className="p-4">
                        <div className="flex items-start justify-between gap-4">
                          <div className="flex items-start gap-3">
                            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-muted">
                              <GitBranch className="h-5 w-5 text-muted-foreground" />
                            </div>
                            <div>
                              <h3 className="font-medium text-foreground">{project.name}</h3>
                              <p className="text-sm text-muted-foreground truncate max-w-md">
                                {project.repoUrl}
                              </p>
                              <div className="flex items-center gap-2 mt-2 flex-wrap">
                                {project.techStack?.slice(0, 4).map((tech) => (
                                  <Badge key={tech} variant="secondary" className="text-xs">
                                    {tech}
                                  </Badge>
                                ))}
                                {project.techStack && project.techStack.length > 4 && (
                                  <Badge variant="outline" className="text-xs">
                                    +{project.techStack.length - 4} more
                                  </Badge>
                                )}
                              </div>
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            <Badge
                              variant="outline"
                              className={
                                project.status === "completed"
                                  ? "bg-success/10 text-success border-success/30"
                                  : project.status === "analyzing"
                                  ? "bg-warning/10 text-warning border-warning/30"
                                  : "bg-muted text-muted-foreground"
                              }
                            >
                              {project.status}
                            </Badge>
                            <Button variant="ghost" size="icon" asChild>
                              <a
                                href={project.repoUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                onClick={(e) => e.stopPropagation()}
                              >
                                <ExternalLink className="h-4 w-4" />
                              </a>
                            </Button>
                            <Button 
                              variant="ghost" 
                              size="icon"
                              onClick={(e) => handleDelete(e, project.id)}
                              disabled={deleteMutation.isPending}
                              data-testid={`button-delete-project-${project.id}`}
                            >
                              <Trash2 className="h-4 w-4 text-destructive" />
                            </Button>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              </ScrollArea>
            ) : (
              <EmptyState
                icon="repo"
                title="No projects yet"
                description="Analyze your first GitHub repository to get started with documentation generation."
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
