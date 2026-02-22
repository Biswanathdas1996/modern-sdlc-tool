import { useState, useEffect, useCallback } from "react";
import { useLocation } from "wouter";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Users,
  UserPlus,
  Shield,
  ShieldCheck,
  Loader2,
  Trash2,
  Key,
  ToggleLeft,
  Check,
  X,
  FolderPlus,
  FolderOpen,
  Pencil,
  GitBranch,
  Settings,
  Info,
  BarChart3,
  TrendingUp,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Target,
  Sparkles,
  ChevronDown,
  ChevronUp,
  FileText,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/hooks/useAuth";
import PromptManagementTab from "@/components/admin/PromptManagementTab";
import { useToast } from "@/hooks/use-toast";
import { apiRequest, queryClient } from "@/lib/queryClient";
import type { Project } from "@shared/schema";

interface Feature {
  key: string;
  label: string;
  category: string;
}

interface UserData {
  id: string;
  username: string;
  email: string;
  role: string;
  is_active: boolean;
  created_at: string;
  permissions: string[];
  project_id: string | null;
  project_ids: string[];
}

interface RagEvaluation {
  id: string;
  projectId: string;
  featureRequestId: string | null;
  brdId: string | null;
  featureTitle: string;
  status: string;
  faithfulness: number | null;
  answerRelevancy: number | null;
  contextRelevancy: number | null;
  contextPrecision: number | null;
  hallucinationScore: number | null;
  overallScore: number | null;
  contextChunksCount: number;
  avgChunkScore: number | null;
  evaluationDetails: Record<string, any>;
  errorMessage: string | null;
  createdAt: string;
  completedAt: string | null;
}

interface RagStats {
  totalEvaluations: number;
  completed: number;
  running: number;
  failed: number;
  pending: number;
  avgFaithfulness: number | null;
  avgAnswerRelevancy: number | null;
  avgContextRelevancy: number | null;
  avgContextPrecision: number | null;
  avgHallucinationScore: number | null;
  avgOverallScore: number | null;
  avgChunksCount: number | null;
  avgRetrievalScore: number | null;
  minOverallScore: number | null;
  maxOverallScore: number | null;
  qualityTiers: Record<string, number>;
  trend: Array<{ date: string; count: number; avgScore: number | null }>;
}

function ScoreBar({ score, label }: { score: number | null; label: string }) {
  if (score === null || score === undefined) return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className="text-muted-foreground">N/A</span>
      </div>
      <div className="h-2 rounded-full bg-muted" />
    </div>
  );
  const pct = Math.round(score * 100);
  const color = pct >= 80 ? "bg-green-500" : pct >= 60 ? "bg-yellow-500" : pct >= 40 ? "bg-orange-500" : "bg-red-500";
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-medium">{pct}%</span>
      </div>
      <div className="h-2 rounded-full bg-muted overflow-hidden">
        <div className={cn("h-full rounded-full transition-all", color)} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const variants: Record<string, string> = {
    completed: "bg-green-500/10 text-green-600 border-green-500/20",
    running: "bg-blue-500/10 text-blue-600 border-blue-500/20",
    pending: "bg-yellow-500/10 text-yellow-600 border-yellow-500/20",
    failed: "bg-red-500/10 text-red-600 border-red-500/20",
  };
  const icons: Record<string, any> = {
    completed: CheckCircle2,
    running: Loader2,
    pending: Clock,
    failed: AlertTriangle,
  };
  const Icon = icons[status] || Clock;
  return (
    <Badge variant="outline" className={cn("gap-1", variants[status] || "")} data-testid={`badge-status-${status}`}>
      <Icon className={cn("h-3 w-3", status === "running" ? "animate-spin" : "")} />
      {status}
    </Badge>
  );
}

function RagMetricsTab({ projects }: { projects: any[] }) {
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const [expandedRow, setExpandedRow] = useState<string | null>(null);

  const effectiveProjectId = selectedProjectId && selectedProjectId !== "all" ? selectedProjectId : "";

  const statsUrl = effectiveProjectId
    ? `/api/ragas/stats?project_id=${effectiveProjectId}`
    : "/api/ragas/stats";

  const evalsUrl = effectiveProjectId
    ? `/api/ragas/evaluations?project_id=${effectiveProjectId}&limit=50`
    : "/api/ragas/evaluations?limit=50";

  const statsQuery = useQuery<{ data: RagStats }>({
    queryKey: [statsUrl],
    refetchInterval: 15000,
  });

  const evalsQuery = useQuery<{ data: RagEvaluation[] }>({
    queryKey: [evalsUrl],
    refetchInterval: 15000,
  });

  const { toast } = useToast();

  const deleteEvalMutation = useMutation({
    mutationFn: async (evalId: string) => {
      await apiRequest("DELETE", `/api/ragas/evaluations/${evalId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [evalsUrl] });
      queryClient.invalidateQueries({ queryKey: [statsUrl] });
      toast({ title: "Evaluation deleted" });
    },
    onError: () => {
      toast({ title: "Failed to delete evaluation", variant: "destructive" });
    },
  });

  const stats = statsQuery.data?.data;
  const evaluations = evalsQuery.data?.data || [];

  const getProjectName = (projectId: string) => {
    const p = projects.find((pr) => pr.id === projectId);
    return p ? p.name : projectId.slice(0, 8);
  };

  return (
    <div className="space-y-4" data-testid="section-rag-metrics">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          RAGAS evaluation metrics for BRD generation quality
        </p>
        <Select value={selectedProjectId} onValueChange={setSelectedProjectId}>
          <SelectTrigger className="w-[200px]" data-testid="select-rag-project">
            <SelectValue placeholder="All Projects" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Projects</SelectItem>
            {projects.map((p) => (
              <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {statsQuery.isLoading ? (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : statsQuery.isError ? (
        <Card>
          <CardContent className="py-8">
            <div className="text-center text-muted-foreground">
              <AlertTriangle className="h-8 w-8 mx-auto mb-2 text-red-500 opacity-50" />
              <p className="text-sm font-medium">Failed to load metrics</p>
              <p className="text-xs mt-1">Please try again later.</p>
            </div>
          </CardContent>
        </Card>
      ) : stats && stats.totalEvaluations > 0 ? (
        <>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <Card>
              <CardContent className="pt-4 pb-3">
                <div className="flex items-center gap-2 mb-1">
                  <Target className="h-4 w-4 text-primary" />
                  <span className="text-xs text-muted-foreground">Overall Score</span>
                </div>
                <div className="text-2xl font-bold" data-testid="text-avg-overall">
                  {stats.avgOverallScore !== null ? `${Math.round(stats.avgOverallScore * 100)}%` : "N/A"}
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  {stats.completed} evaluations
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4 pb-3">
                <div className="flex items-center gap-2 mb-1">
                  <Sparkles className="h-4 w-4 text-green-500" />
                  <span className="text-xs text-muted-foreground">Faithfulness</span>
                </div>
                <div className="text-2xl font-bold" data-testid="text-avg-faithfulness">
                  {stats.avgFaithfulness !== null ? `${Math.round(stats.avgFaithfulness * 100)}%` : "N/A"}
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4 pb-3">
                <div className="flex items-center gap-2 mb-1">
                  <TrendingUp className="h-4 w-4 text-blue-500" />
                  <span className="text-xs text-muted-foreground">Answer Relevancy</span>
                </div>
                <div className="text-2xl font-bold" data-testid="text-avg-relevancy">
                  {stats.avgAnswerRelevancy !== null ? `${Math.round(stats.avgAnswerRelevancy * 100)}%` : "N/A"}
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4 pb-3">
                <div className="flex items-center gap-2 mb-1">
                  <AlertTriangle className="h-4 w-4 text-orange-500" />
                  <span className="text-xs text-muted-foreground">Hallucination</span>
                </div>
                <div className="text-2xl font-bold" data-testid="text-avg-hallucination">
                  {stats.avgHallucinationScore !== null ? `${Math.round(stats.avgHallucinationScore * 100)}%` : "N/A"}
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  higher = less hallucination
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4 pb-3">
                <div className="flex items-center gap-2 mb-1">
                  <BarChart3 className="h-4 w-4 text-purple-500" />
                  <span className="text-xs text-muted-foreground">Context Quality</span>
                </div>
                <div className="text-2xl font-bold" data-testid="text-avg-context">
                  {stats.avgContextRelevancy !== null ? `${Math.round(stats.avgContextRelevancy * 100)}%` : "N/A"}
                </div>
              </CardContent>
            </Card>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <BarChart3 className="h-4 w-4" />
                  Average Scores
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <ScoreBar score={stats.avgFaithfulness} label="Faithfulness" />
                <ScoreBar score={stats.avgAnswerRelevancy} label="Answer Relevancy" />
                <ScoreBar score={stats.avgHallucinationScore} label="Hallucination (higher = less)" />
                <ScoreBar score={stats.avgContextRelevancy} label="Context Relevancy" />
                <ScoreBar score={stats.avgContextPrecision} label="Context Precision" />
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Info className="h-4 w-4" />
                  Quality Distribution
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  {[
                    { tier: "excellent", label: "Excellent (80%+)", color: "text-green-600" },
                    { tier: "good", label: "Good (60-79%)", color: "text-blue-600" },
                    { tier: "fair", label: "Fair (40-59%)", color: "text-yellow-600" },
                    { tier: "poor", label: "Poor (<40%)", color: "text-red-600" },
                  ].map(({ tier, label, color }) => (
                    <div key={tier} className="space-y-1">
                      <p className={cn("text-xs font-medium", color)}>{label}</p>
                      <p className="text-lg font-bold" data-testid={`text-tier-${tier}`}>
                        {stats.qualityTiers?.[tier] || 0}
                      </p>
                    </div>
                  ))}
                </div>
                <div className="border-t pt-2 mt-2">
                  <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
                    <div>Avg Chunks: <span className="font-medium text-foreground">{stats.avgChunksCount?.toFixed(1) || "N/A"}</span></div>
                    <div>Avg Retrieval: <span className="font-medium text-foreground">{stats.avgRetrievalScore ? `${Math.round(stats.avgRetrievalScore * 100)}%` : "N/A"}</span></div>
                    <div>Running: <span className="font-medium text-foreground">{stats.running}</span></div>
                    <div>Failed: <span className="font-medium text-foreground">{stats.failed}</span></div>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </>
      ) : (
        <Card>
          <CardContent className="py-8">
            <div className="text-center text-muted-foreground">
              <BarChart3 className="h-8 w-8 mx-auto mb-2 opacity-50" />
              <p className="text-sm font-medium">No RAGAS Evaluations Yet</p>
              <p className="text-xs mt-1">Evaluations are automatically triggered when BRDs are generated with knowledge base context.</p>
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2">
            <Clock className="h-4 w-4" />
            Recent Evaluations ({evaluations.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {evalsQuery.isLoading ? (
            <div className="flex items-center justify-center py-4">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : evalsQuery.isError ? (
            <p className="text-sm text-red-500 text-center py-4">
              Failed to load evaluations
            </p>
          ) : evaluations.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-4">
              No evaluations recorded yet
            </p>
          ) : (
            <div className="space-y-2">
              {evaluations.map((ev) => (
                <div key={ev.id} className="border rounded-lg" data-testid={`row-eval-${ev.id}`}>
                  <div
                    className="flex items-center justify-between p-3 cursor-pointer hover:bg-muted/50 transition-colors"
                    onClick={() => setExpandedRow(expandedRow === ev.id ? null : ev.id)}
                    data-testid={`button-expand-${ev.id}`}
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <StatusBadge status={ev.status} />
                      <div className="min-w-0">
                        <p className="text-sm font-medium truncate" data-testid={`text-title-${ev.id}`}>
                          {ev.featureTitle || "Untitled"}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {getProjectName(ev.projectId)} &middot; {new Date(ev.createdAt).toLocaleDateString()}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      {ev.overallScore !== null && (
                        <div className={cn(
                          "text-sm font-bold px-2 py-0.5 rounded",
                          ev.overallScore >= 0.8 ? "bg-green-500/10 text-green-600" :
                          ev.overallScore >= 0.6 ? "bg-blue-500/10 text-blue-600" :
                          ev.overallScore >= 0.4 ? "bg-yellow-500/10 text-yellow-600" :
                          "bg-red-500/10 text-red-600"
                        )} data-testid={`text-score-${ev.id}`}>
                          {Math.round(ev.overallScore * 100)}%
                        </div>
                      )}
                      <button
                        className="p-1 rounded hover:bg-destructive/10 transition-colors"
                        data-testid={`button-delete-eval-${ev.id}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          if (confirm("Delete this evaluation record?")) {
                            deleteEvalMutation.mutate(ev.id);
                          }
                        }}
                      >
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </button>
                      {expandedRow === ev.id ? (
                        <ChevronUp className="h-4 w-4 text-muted-foreground" />
                      ) : (
                        <ChevronDown className="h-4 w-4 text-muted-foreground" />
                      )}
                    </div>
                  </div>
                  {expandedRow === ev.id && (
                    <div className="px-3 pb-3 border-t pt-3 space-y-3" data-testid={`detail-${ev.id}`}>
                      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                        <ScoreBar score={ev.faithfulness} label="Faithfulness" />
                        <ScoreBar score={ev.answerRelevancy} label="Answer Relevancy" />
                        <ScoreBar score={ev.hallucinationScore} label="Hallucination" />
                        <ScoreBar score={ev.contextRelevancy} label="Context Relevancy" />
                        <ScoreBar score={ev.contextPrecision} label="Context Precision" />
                      </div>
                      <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
                        <div>Chunks Retrieved: <span className="font-medium text-foreground">{ev.contextChunksCount}</span></div>
                        <div>Avg Chunk Score: <span className="font-medium text-foreground">{ev.avgChunkScore ? `${Math.round(ev.avgChunkScore * 100)}%` : "N/A"}</span></div>
                        {ev.completedAt && <div>Completed: <span className="font-medium text-foreground">{new Date(ev.completedAt).toLocaleString()}</span></div>}
                        {ev.errorMessage && <div className="col-span-2 text-red-500">Error: {ev.errorMessage}</div>}
                      </div>
                      {ev.evaluationDetails && Object.keys(ev.evaluationDetails).length > 0 && (
                        <div className="space-y-2">
                          <p className="text-xs font-medium text-muted-foreground">Evaluation Reasoning</p>
                          {Object.entries(ev.evaluationDetails).map(([metric, detail]: [string, any]) => (
                            detail?.reasoning && (
                              <div key={metric} className="text-xs bg-muted/50 rounded p-2">
                                <span className="font-medium capitalize">{metric.replace(/_/g, " ")}:</span>{" "}
                                {detail.reasoning}
                              </div>
                            )
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default function AdminPage({ initialTab = "projects" }: { initialTab?: string }) {
  const [, navigate] = useLocation();
  const { user: currentUser } = useAuth();
  const { toast } = useToast();

  const handleTabChange = useCallback((tab: string) => {
    navigate(`/admin/${tab}`);
  }, [navigate]);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [showPermissionsDialog, setShowPermissionsDialog] = useState(false);
  const [showPasswordDialog, setShowPasswordDialog] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [selectedUser, setSelectedUser] = useState<UserData | null>(null);
  const [selectedPermissions, setSelectedPermissions] = useState<string[]>([]);

  const [newUsername, setNewUsername] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRole, setNewRole] = useState("user");
  const [newFeatures, setNewFeatures] = useState<string[]>([]);
  const [newProjectId, setNewProjectId] = useState<string>("");
  const [resetPassword, setResetPassword] = useState("");

  const [showCreateProjectDialog, setShowCreateProjectDialog] = useState(false);
  const [showEditProjectDialog, setShowEditProjectDialog] = useState(false);
  const [showDeleteProjectDialog, setShowDeleteProjectDialog] = useState(false);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [projectName, setProjectName] = useState("");
  const [projectRepoUrl, setProjectRepoUrl] = useState("");
  const [projectDescription, setProjectDescription] = useState("");
  const [projectStatus, setProjectStatus] = useState<string>("pending");

  useEffect(() => {
    document.title = "Admin Dashboard | Defuse 2.O";
  }, []);

  const { data: users = [], isLoading: usersLoading } = useQuery<UserData[]>({
    queryKey: ["/api/admin/users"],
  });

  const { data: features = [] } = useQuery<Feature[]>({
    queryKey: ["/api/auth/features"],
  });

  const { data: projects = [], isLoading: projectsLoading } = useQuery<Project[]>({
    queryKey: ["/api/projects"],
  });

  const createProjectMutation = useMutation({
    mutationFn: async (data: { name: string; repoUrl: string; description: string; status: string }) => {
      const res = await apiRequest("POST", "/api/projects", { ...data, techStack: [] });
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/projects"] });
      setShowCreateProjectDialog(false);
      setProjectName("");
      setProjectRepoUrl("");
      setProjectDescription("");
      setProjectStatus("pending");
      toast({ title: "Project created", description: "New project has been added" });
    },
    onError: (err: Error) => {
      toast({ title: "Failed to create project", description: err.message, variant: "destructive" });
    },
  });

  const updateProjectMutation = useMutation({
    mutationFn: async ({ id, ...data }: { id: string; name: string; repoUrl: string; description: string; status: string }) => {
      const res = await apiRequest("PATCH", `/api/projects/${id}`, data);
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/projects"] });
      setShowEditProjectDialog(false);
      toast({ title: "Project updated", description: "Project details saved" });
    },
    onError: (err: Error) => {
      toast({ title: "Failed to update project", description: err.message, variant: "destructive" });
    },
  });

  const deleteProjectMutation = useMutation({
    mutationFn: async (projectId: string) => {
      const res = await apiRequest("DELETE", `/api/projects/${projectId}`);
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/projects"] });
      setShowDeleteProjectDialog(false);
      toast({ title: "Project deleted", description: "Project has been removed" });
    },
    onError: (err: Error) => {
      toast({ title: "Failed to delete project", description: err.message, variant: "destructive" });
    },
  });

  const openEditProject = (p: Project) => {
    setSelectedProject(p);
    setProjectName(p.name);
    setProjectRepoUrl(p.repoUrl || "");
    setProjectDescription(p.description || "");
    setProjectStatus(p.status);
    setShowEditProjectDialog(true);
  };

  const createUserMutation = useMutation({
    mutationFn: async (data: { username: string; email: string; password: string; role: string; features: string[]; project_id?: string }) => {
      const res = await apiRequest("POST", "/api/admin/users", data);
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/admin/users"] });
      setShowCreateDialog(false);
      setNewUsername("");
      setNewEmail("");
      setNewPassword("");
      setNewRole("user");
      setNewFeatures([]);
      setNewProjectId("");
      toast({ title: "User created", description: "New user account has been created" });
    },
    onError: (err: Error) => {
      toast({ title: "Failed to create user", description: err.message, variant: "destructive" });
    },
  });

  const updatePermissionsMutation = useMutation({
    mutationFn: async ({ userId, features }: { userId: string; features: string[] }) => {
      const res = await apiRequest("PATCH", `/api/admin/users/${userId}/permissions`, { features });
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/admin/users"] });
      setShowPermissionsDialog(false);
      toast({ title: "Permissions updated", description: "User permissions have been saved" });
    },
    onError: (err: Error) => {
      toast({ title: "Failed to update permissions", description: err.message, variant: "destructive" });
    },
  });

  const toggleStatusMutation = useMutation({
    mutationFn: async ({ userId, isActive }: { userId: string; isActive: boolean }) => {
      const res = await apiRequest("PATCH", `/api/admin/users/${userId}/status`, { is_active: isActive });
      return res.json();
    },
    onSuccess: (_, vars) => {
      queryClient.invalidateQueries({ queryKey: ["/api/admin/users"] });
      toast({
        title: vars.isActive ? "User activated" : "User deactivated",
        description: `Account has been ${vars.isActive ? "activated" : "deactivated"}`,
      });
    },
    onError: (err: Error) => {
      toast({ title: "Failed to update status", description: err.message, variant: "destructive" });
    },
  });

  const resetPasswordMutation = useMutation({
    mutationFn: async ({ userId, password }: { userId: string; password: string }) => {
      const res = await apiRequest("PATCH", `/api/admin/users/${userId}/password`, { password });
      return res.json();
    },
    onSuccess: () => {
      setShowPasswordDialog(false);
      setResetPassword("");
      toast({ title: "Password reset", description: "User password has been updated" });
    },
    onError: (err: Error) => {
      toast({ title: "Failed to reset password", description: err.message, variant: "destructive" });
    },
  });

  const deleteUserMutation = useMutation({
    mutationFn: async (userId: string) => {
      const res = await apiRequest("DELETE", `/api/admin/users/${userId}`);
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/admin/users"] });
      setShowDeleteDialog(false);
      toast({ title: "User deleted", description: "User account has been removed" });
    },
    onError: (err: Error) => {
      toast({ title: "Failed to delete user", description: err.message, variant: "destructive" });
    },
  });

  const openPermissions = (u: UserData) => {
    setSelectedUser(u);
    setSelectedPermissions([...u.permissions]);
    setShowPermissionsDialog(true);
  };

  const toggleFeature = (key: string) => {
    setSelectedPermissions(prev =>
      prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key]
    );
  };

  const toggleNewFeature = (key: string) => {
    setNewFeatures(prev =>
      prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key]
    );
  };

  const groupedFeatures = features.reduce<Record<string, Feature[]>>((acc, f) => {
    if (!acc[f.category]) acc[f.category] = [];
    acc[f.category].push(f);
    return acc;
  }, {});

  const categoryLabels: Record<string, string> = {
    prerequisite: "Pre-requisite Steps",
    workflow: "Workflow Steps",
    tools: "Tools",
    agents: "AI Agents",
  };

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-5xl mx-auto p-6 space-y-6">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary">
            <Shield className="h-5 w-5 text-primary-foreground" />
          </div>
          <div>
            <h1 className="text-2xl font-bold" data-testid="text-admin-title">Admin Dashboard</h1>
            <p className="text-sm text-muted-foreground">
              Manage projects, users, and feature access
            </p>
          </div>
        </div>

        <Tabs value={initialTab} onValueChange={handleTabChange} className="w-full">
          <TabsList data-testid="tabs-admin">
            <TabsTrigger value="projects" data-testid="tab-projects">
              <FolderOpen className="h-4 w-4 mr-2" />
              Projects ({projects.length})
            </TabsTrigger>
            <TabsTrigger value="users" data-testid="tab-users">
              <Users className="h-4 w-4 mr-2" />
              Users ({users.length})
            </TabsTrigger>
            <TabsTrigger value="rag-metrics" data-testid="tab-rag-metrics">
              <BarChart3 className="h-4 w-4 mr-2" />
              RAG Metrics
            </TabsTrigger>
            <TabsTrigger value="prompts" data-testid="tab-prompts">
              <FileText className="h-4 w-4 mr-2" />
              Prompts
            </TabsTrigger>
            <TabsTrigger value="settings" data-testid="tab-settings">
              <Settings className="h-4 w-4 mr-2" />
              Settings
            </TabsTrigger>
          </TabsList>

          <TabsContent value="projects" className="space-y-4 mt-4">
            <div className="flex items-center justify-between">
              <p className="text-sm text-muted-foreground">Create and manage projects for repository analysis and documentation</p>
              <Button onClick={() => setShowCreateProjectDialog(true)} data-testid="button-create-project">
                <FolderPlus className="h-4 w-4 mr-2" />
                Create Project
              </Button>
            </div>
            <Card>
              <CardContent className="pt-6">
                {projectsLoading ? (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                  </div>
                ) : projects.length === 0 ? (
                  <div className="text-center py-12">
                    <FolderOpen className="h-10 w-10 mx-auto text-muted-foreground mb-3" />
                    <p className="text-sm text-muted-foreground">No projects yet</p>
                    <p className="text-xs text-muted-foreground mt-1">Create a project to get started with repository analysis</p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {projects.map((p) => (
                      <div
                        key={p.id}
                        className="p-4 rounded-md border border-border space-y-0"
                        data-testid={`project-row-${p.id}`}
                      >
                        <div className="flex items-center justify-between gap-3">
                          <div className="flex items-center gap-3 min-w-0">
                            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
                              <GitBranch className="h-4 w-4" />
                            </div>
                            <div className="min-w-0">
                              <div className="flex items-center gap-2 flex-wrap">
                                <span className="font-medium text-sm">{p.name}</span>
                                <Badge
                                  variant="outline"
                                  className={cn(
                                    "text-xs",
                                    p.status === "completed" && "bg-success/10 text-success border-success/30",
                                    p.status === "analyzing" && "bg-warning/10 text-warning border-warning/30",
                                    p.status === "error" && "bg-destructive/10 text-destructive border-destructive/30",
                                    p.status === "pending" && "bg-muted text-muted-foreground"
                                  )}
                                >
                                  {p.status}
                                </Badge>
                              </div>
                              {p.description && (
                                <p className="text-xs text-muted-foreground truncate mt-0.5">{p.description}</p>
                              )}
                              {p.repoUrl && (
                                <p className="text-xs text-muted-foreground truncate">{p.repoUrl}</p>
                              )}
                            </div>
                          </div>
                          <div className="flex items-center gap-1">
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => openEditProject(p)}
                              title="Edit project"
                              data-testid={`button-edit-project-${p.id}`}
                            >
                              <Pencil className="h-4 w-4" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => { setSelectedProject(p); setShowDeleteProjectDialog(true); }}
                              title="Delete project"
                              data-testid={`button-delete-project-${p.id}`}
                            >
                              <Trash2 className="h-4 w-4 text-destructive" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => { setNewProjectId(p.id); setNewRole("user"); setShowCreateDialog(true); }}
                              title="Add user to project"
                              data-testid={`button-add-user-${p.id}`}
                            >
                              <UserPlus className="h-4 w-4" />
                            </Button>
                          </div>
                        </div>
                        {users.filter(u => u.project_ids?.includes(p.id)).length > 0 && (
                          <div className="mt-2 pt-2 border-t border-border/50">
                            <p className="text-xs text-muted-foreground mb-1.5">Assigned Users:</p>
                            <div className="flex flex-wrap gap-2">
                              {users.filter(u => u.project_ids?.includes(p.id)).map(u => (
                                <Badge key={u.id} variant="secondary" className="text-xs" data-testid={`badge-user-${u.username}-project-${p.id}`}>
                                  {u.username}
                                </Badge>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="users" className="space-y-4 mt-4">
            <div className="flex items-center justify-between">
              <p className="text-sm text-muted-foreground">Manage user accounts and feature permissions</p>
              <Button onClick={() => setShowCreateDialog(true)} data-testid="button-create-user">
                <UserPlus className="h-4 w-4 mr-2" />
                Create User
              </Button>
            </div>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Users className="h-4 w-4" />
              Users ({users.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            {usersLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : users.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-8">No users found</p>
            ) : (
              <div className="space-y-3">
                {users.map((u) => (
                  <div
                    key={u.id}
                    className={cn(
                      "flex items-center justify-between gap-3 p-4 rounded-md border border-border flex-wrap",
                      !u.is_active && "opacity-60"
                    )}
                    data-testid={`user-row-${u.username}`}
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <div className={cn(
                        "flex h-9 w-9 shrink-0 items-center justify-center rounded-full",
                        u.role === "admin" ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"
                      )}>
                        {u.role === "admin" ? <ShieldCheck className="h-4 w-4" /> : <Users className="h-4 w-4" />}
                      </div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-medium text-sm">{u.username}</span>
                          <Badge variant={u.role === "admin" ? "default" : "secondary"} className="text-xs">
                            {u.role}
                          </Badge>
                          {!u.is_active && (
                            <Badge variant="outline" className="text-xs text-destructive border-destructive/30">
                              Disabled
                            </Badge>
                          )}
                        </div>
                        <p className="text-xs text-muted-foreground truncate">{u.email}</p>
                        {u.project_ids && u.project_ids.length > 0 && (
                          <p className="text-xs text-muted-foreground truncate">
                            Projects: {u.project_ids.map(pid => projects.find(p => p.id === pid)?.name || pid).join(", ")}
                          </p>
                        )}
                        <div className="flex items-center gap-1 mt-1 flex-wrap">
                          <span className="text-xs text-muted-foreground">{u.permissions.length} features</span>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-1">
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => openPermissions(u)}
                        title="Manage permissions"
                        data-testid={`button-permissions-${u.username}`}
                      >
                        <ShieldCheck className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => { setSelectedUser(u); setShowPasswordDialog(true); }}
                        title="Reset password"
                        data-testid={`button-reset-pwd-${u.username}`}
                      >
                        <Key className="h-4 w-4" />
                      </Button>
                      {u.id !== currentUser?.id && (
                        <>
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => toggleStatusMutation.mutate({ userId: u.id, isActive: !u.is_active })}
                            title={u.is_active ? "Deactivate" : "Activate"}
                            data-testid={`button-toggle-${u.username}`}
                          >
                            <ToggleLeft className={cn("h-4 w-4", u.is_active ? "text-green-500" : "text-muted-foreground")} />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => { setSelectedUser(u); setShowDeleteDialog(true); }}
                            title="Delete user"
                            data-testid={`button-delete-${u.username}`}
                          >
                            <Trash2 className="h-4 w-4 text-destructive" />
                          </Button>
                        </>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
          <DialogContent className="sm:max-w-lg" data-testid="dialog-create-user">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <UserPlus className="h-5 w-5" />
                Create New User
              </DialogTitle>
              <DialogDescription>
                Add a new user and assign their feature access
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-2">
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-2">
                  <Label htmlFor="create-username">Username</Label>
                  <Input
                    id="create-username"
                    value={newUsername}
                    onChange={(e) => setNewUsername(e.target.value)}
                    placeholder="johndoe"
                    data-testid="input-create-username"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="create-role">Role</Label>
                  <Select value={newRole} onValueChange={setNewRole}>
                    <SelectTrigger data-testid="select-create-role">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="user">User</SelectItem>
                      <SelectItem value="admin">Admin</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="create-email">Email</Label>
                <Input
                  id="create-email"
                  type="email"
                  value={newEmail}
                  onChange={(e) => setNewEmail(e.target.value)}
                  placeholder="john@example.com"
                  data-testid="input-create-email"
                />
              </div>
              {newRole === "user" && (
                <div className="space-y-2">
                  <Label htmlFor="create-project">Assign to Project</Label>
                  <Select value={newProjectId} onValueChange={setNewProjectId}>
                    <SelectTrigger data-testid="select-create-project">
                      <SelectValue placeholder="Select a project" />
                    </SelectTrigger>
                    <SelectContent>
                      {projects.map((p) => (
                        <SelectItem key={p.id} value={p.id} data-testid={`option-create-project-${p.id}`}>
                          {p.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}
              <div className="space-y-2">
                <Label htmlFor="create-password">Password</Label>
                <Input
                  id="create-password"
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="Minimum 6 characters"
                  data-testid="input-create-password"
                />
              </div>

              {newRole === "user" && (
                <div className="space-y-3">
                  <Label>Feature Access</Label>
                  <div className="max-h-48 overflow-y-auto space-y-3 border border-border rounded-md p-3">
                    {Object.entries(groupedFeatures).map(([category, feats]) => (
                      <div key={category}>
                        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-1.5">
                          {categoryLabels[category] || category}
                        </p>
                        <div className="space-y-1">
                          {feats.map((f) => (
                            <label
                              key={f.key}
                              className="flex items-center justify-between gap-2 py-1 cursor-pointer"
                            >
                              <span className="text-sm">{f.label}</span>
                              <Switch
                                checked={newFeatures.includes(f.key)}
                                onCheckedChange={() => toggleNewFeature(f.key)}
                                data-testid={`switch-create-${f.key}`}
                              />
                            </label>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => setNewFeatures(features.map(f => f.key))}
                      data-testid="button-select-all-create"
                    >
                      <Check className="h-3 w-3 mr-1" />
                      Select All
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => setNewFeatures([])}
                      data-testid="button-clear-all-create"
                    >
                      <X className="h-3 w-3 mr-1" />
                      Clear All
                    </Button>
                  </div>
                </div>
              )}
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setShowCreateDialog(false)}>Cancel</Button>
              <Button
                onClick={() => createUserMutation.mutate({
                  username: newUsername.trim(),
                  email: newEmail.trim(),
                  password: newPassword,
                  role: newRole,
                  features: newRole === "admin" ? features.map(f => f.key) : newFeatures,
                  project_id: newRole === "user" ? newProjectId : undefined,
                })}
                disabled={!newUsername.trim() || !newEmail.trim() || !newPassword || newPassword.length < 6 || (newRole === "user" && !newProjectId) || createUserMutation.isPending}
                data-testid="button-submit-create"
              >
                {createUserMutation.isPending ? (
                  <><Loader2 className="h-4 w-4 animate-spin mr-2" />Creating...</>
                ) : (
                  "Create User"
                )}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        <Dialog open={showPermissionsDialog} onOpenChange={setShowPermissionsDialog}>
          <DialogContent className="sm:max-w-lg" data-testid="dialog-permissions">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <ShieldCheck className="h-5 w-5" />
                Manage Permissions
              </DialogTitle>
              <DialogDescription>
                {selectedUser && `Configure feature access for ${selectedUser.username}`}
              </DialogDescription>
            </DialogHeader>
            <div className="max-h-72 overflow-y-auto space-y-3 py-2">
              {Object.entries(groupedFeatures).map(([category, feats]) => (
                <div key={category}>
                  <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-1.5">
                    {categoryLabels[category] || category}
                  </p>
                  <div className="space-y-1">
                    {feats.map((f) => (
                      <label
                        key={f.key}
                        className="flex items-center justify-between gap-2 py-1 cursor-pointer"
                      >
                        <span className="text-sm">{f.label}</span>
                        <Switch
                          checked={selectedPermissions.includes(f.key)}
                          onCheckedChange={() => toggleFeature(f.key)}
                          data-testid={`switch-perm-${f.key}`}
                        />
                      </label>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            <div className="flex gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setSelectedPermissions(features.map(f => f.key))}
                data-testid="button-select-all-perms"
              >
                <Check className="h-3 w-3 mr-1" />
                Select All
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setSelectedPermissions([])}
                data-testid="button-clear-all-perms"
              >
                <X className="h-3 w-3 mr-1" />
                Clear All
              </Button>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setShowPermissionsDialog(false)}>Cancel</Button>
              <Button
                onClick={() => selectedUser && updatePermissionsMutation.mutate({
                  userId: selectedUser.id,
                  features: selectedPermissions,
                })}
                disabled={updatePermissionsMutation.isPending}
                data-testid="button-save-permissions"
              >
                {updatePermissionsMutation.isPending ? (
                  <><Loader2 className="h-4 w-4 animate-spin mr-2" />Saving...</>
                ) : (
                  "Save Permissions"
                )}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        <Dialog open={showPasswordDialog} onOpenChange={setShowPasswordDialog}>
          <DialogContent className="sm:max-w-sm" data-testid="dialog-reset-password">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Key className="h-5 w-5" />
                Reset Password
              </DialogTitle>
              <DialogDescription>
                {selectedUser && `Set a new password for ${selectedUser.username}`}
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-3 py-2">
              <div className="space-y-2">
                <Label htmlFor="reset-password">New Password</Label>
                <Input
                  id="reset-password"
                  type="password"
                  value={resetPassword}
                  onChange={(e) => setResetPassword(e.target.value)}
                  placeholder="Minimum 6 characters"
                  data-testid="input-reset-password"
                />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => { setShowPasswordDialog(false); setResetPassword(""); }}>Cancel</Button>
              <Button
                onClick={() => selectedUser && resetPasswordMutation.mutate({ userId: selectedUser.id, password: resetPassword })}
                disabled={!resetPassword || resetPassword.length < 6 || resetPasswordMutation.isPending}
                data-testid="button-submit-reset-password"
              >
                {resetPasswordMutation.isPending ? (
                  <><Loader2 className="h-4 w-4 animate-spin mr-2" />Resetting...</>
                ) : (
                  "Reset Password"
                )}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        <Dialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
          <DialogContent className="sm:max-w-sm" data-testid="dialog-delete-user">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Trash2 className="h-5 w-5 text-destructive" />
                Delete User
              </DialogTitle>
              <DialogDescription>
                {selectedUser && `Are you sure you want to delete ${selectedUser.username}? This action cannot be undone.`}
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button variant="outline" onClick={() => setShowDeleteDialog(false)}>Cancel</Button>
              <Button
                variant="destructive"
                onClick={() => selectedUser && deleteUserMutation.mutate(selectedUser.id)}
                disabled={deleteUserMutation.isPending}
                data-testid="button-confirm-delete"
              >
                {deleteUserMutation.isPending ? (
                  <><Loader2 className="h-4 w-4 animate-spin mr-2" />Deleting...</>
                ) : (
                  "Delete User"
                )}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

          </TabsContent>

          <TabsContent value="rag-metrics" className="space-y-4 mt-4">
            <RagMetricsTab projects={projects} />
          </TabsContent>

          <TabsContent value="prompts" className="space-y-4 mt-4">
            <PromptManagementTab />
          </TabsContent>

          <TabsContent value="settings" className="space-y-4 mt-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  <Info className="h-4 w-4" />
                  System Information
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <p className="text-xs text-muted-foreground">Application</p>
                    <p className="text-sm font-medium">Defuse 2.O</p>
                  </div>
                  <div className="space-y-1">
                    <p className="text-xs text-muted-foreground">Total Projects</p>
                    <p className="text-sm font-medium">{projects.length}</p>
                  </div>
                  <div className="space-y-1">
                    <p className="text-xs text-muted-foreground">Total Users</p>
                    <p className="text-sm font-medium">{users.length}</p>
                  </div>
                  <div className="space-y-1">
                    <p className="text-xs text-muted-foreground">Active Users</p>
                    <p className="text-sm font-medium">{users.filter(u => u.is_active).length}</p>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  <Shield className="h-4 w-4" />
                  Feature Configuration
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {Object.entries(groupedFeatures).map(([category, feats]) => (
                    <div key={category}>
                      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-1.5">
                        {categoryLabels[category] || category}
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {feats.map((f) => (
                          <Badge key={f.key} variant="secondary" className="text-xs" data-testid={`badge-feature-${f.key}`}>
                            {f.label}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>

        <Dialog open={showCreateProjectDialog} onOpenChange={setShowCreateProjectDialog}>
          <DialogContent className="sm:max-w-lg" data-testid="dialog-create-project">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <FolderPlus className="h-5 w-5" />
                Create New Project
              </DialogTitle>
              <DialogDescription>
                Add a new project manually or later connect it to a GitHub repository
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-2">
              <div className="space-y-2">
                <Label htmlFor="project-name">Project Name</Label>
                <Input
                  id="project-name"
                  value={projectName}
                  onChange={(e) => setProjectName(e.target.value)}
                  placeholder="My Project"
                  data-testid="input-project-name"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="project-repo">Repository URL (optional)</Label>
                <Input
                  id="project-repo"
                  value={projectRepoUrl}
                  onChange={(e) => setProjectRepoUrl(e.target.value)}
                  placeholder="https://github.com/owner/repo"
                  data-testid="input-project-repo"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="project-desc">Description</Label>
                <Textarea
                  id="project-desc"
                  value={projectDescription}
                  onChange={(e) => setProjectDescription(e.target.value)}
                  placeholder="Brief description of the project"
                  rows={3}
                  data-testid="input-project-description"
                />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setShowCreateProjectDialog(false)}>Cancel</Button>
              <Button
                onClick={() => createProjectMutation.mutate({
                  name: projectName.trim(),
                  repoUrl: projectRepoUrl.trim(),
                  description: projectDescription.trim(),
                  status: "pending",
                })}
                disabled={!projectName.trim() || createProjectMutation.isPending}
                data-testid="button-submit-create-project"
              >
                {createProjectMutation.isPending ? (
                  <><Loader2 className="h-4 w-4 animate-spin mr-2" />Creating...</>
                ) : (
                  "Create Project"
                )}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        <Dialog open={showEditProjectDialog} onOpenChange={setShowEditProjectDialog}>
          <DialogContent className="sm:max-w-lg" data-testid="dialog-edit-project">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Pencil className="h-5 w-5" />
                Edit Project
              </DialogTitle>
              <DialogDescription>
                {selectedProject && `Update details for ${selectedProject.name}`}
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-2">
              <div className="space-y-2">
                <Label htmlFor="edit-project-name">Project Name</Label>
                <Input
                  id="edit-project-name"
                  value={projectName}
                  onChange={(e) => setProjectName(e.target.value)}
                  data-testid="input-edit-project-name"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-project-repo">Repository URL</Label>
                <Input
                  id="edit-project-repo"
                  value={projectRepoUrl}
                  onChange={(e) => setProjectRepoUrl(e.target.value)}
                  placeholder="https://github.com/owner/repo"
                  data-testid="input-edit-project-repo"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-project-desc">Description</Label>
                <Textarea
                  id="edit-project-desc"
                  value={projectDescription}
                  onChange={(e) => setProjectDescription(e.target.value)}
                  rows={3}
                  data-testid="input-edit-project-description"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-project-status">Status</Label>
                <Select value={projectStatus} onValueChange={setProjectStatus}>
                  <SelectTrigger data-testid="select-edit-project-status">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="pending">Pending</SelectItem>
                    <SelectItem value="analyzing">Analyzing</SelectItem>
                    <SelectItem value="completed">Completed</SelectItem>
                    <SelectItem value="error">Error</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setShowEditProjectDialog(false)}>Cancel</Button>
              <Button
                onClick={() => selectedProject && updateProjectMutation.mutate({
                  id: selectedProject.id,
                  name: projectName.trim(),
                  repoUrl: projectRepoUrl.trim(),
                  description: projectDescription.trim(),
                  status: projectStatus,
                })}
                disabled={!projectName.trim() || updateProjectMutation.isPending}
                data-testid="button-submit-edit-project"
              >
                {updateProjectMutation.isPending ? (
                  <><Loader2 className="h-4 w-4 animate-spin mr-2" />Saving...</>
                ) : (
                  "Save Changes"
                )}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        <Dialog open={showDeleteProjectDialog} onOpenChange={setShowDeleteProjectDialog}>
          <DialogContent className="sm:max-w-sm" data-testid="dialog-delete-project">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Trash2 className="h-5 w-5 text-destructive" />
                Delete Project
              </DialogTitle>
              <DialogDescription>
                {selectedProject && `Are you sure you want to delete "${selectedProject.name}"? All associated data will be removed. This cannot be undone.`}
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button variant="outline" onClick={() => setShowDeleteProjectDialog(false)}>Cancel</Button>
              <Button
                variant="destructive"
                onClick={() => selectedProject && deleteProjectMutation.mutate(selectedProject.id)}
                disabled={deleteProjectMutation.isPending}
                data-testid="button-confirm-delete-project"
              >
                {deleteProjectMutation.isPending ? (
                  <><Loader2 className="h-4 w-4 animate-spin mr-2" />Deleting...</>
                ) : (
                  "Delete Project"
                )}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  );
}
