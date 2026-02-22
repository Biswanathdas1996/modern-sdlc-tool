import { useLocation, useSearch, Link } from "wouter";
import {
  GitBranch,
  FileText,
  ClipboardList,
  FileCheck,
  TestTube,
  Database,
  ChevronRight,
  Sparkles,
  Bookmark,
  Library,
  Bot,
  Shield,
  FlaskConical,
  Globe,
  Code2,
  Settings,
  LogOut,
  User,
  ChevronsUpDown,
  FolderOpen,
  Users,
  FolderKanban,
  History,
  BarChart3,
} from "lucide-react";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarGroupContent,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
  SidebarHeader,
  SidebarFooter,
} from "@/components/ui/sidebar";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useAuth } from "@/hooks/useAuth";
import { useProject } from "@/hooks/useProject";

interface WorkflowStep {
  id: string;
  featureKey: string;
  title: string;
  description: string;
  path: string;
  icon: React.ElementType;
  step: number;
}

const prerequisiteSteps: WorkflowStep[] = [
  {
    id: "analyze",
    featureKey: "analyze",
    title: "Analyze Repository",
    description: "Connect and analyze GitHub repo",
    path: "/",
    icon: GitBranch,
    step: 1,
  },
  {
    id: "document",
    featureKey: "documentation",
    title: "Documentation",
    description: "View generated docs",
    path: "/documentation",
    icon: FileText,
    step: 2,
  },
];

const workflowSteps: WorkflowStep[] = [
  {
    id: "requirements",
    featureKey: "requirements",
    title: "Feature Request",
    description: "Input new requirements",
    path: "/requirements",
    icon: ClipboardList,
    step: 3,
  },
  {
    id: "brd",
    featureKey: "brd",
    title: "Generate BRD",
    description: "Create business requirements",
    path: "/brd",
    icon: FileCheck,
    step: 4,
  },
  {
    id: "user-stories",
    featureKey: "user_stories",
    title: "User Stories",
    description: "Generate stories for JIRA",
    path: "/user-stories",
    icon: Bookmark,
    step: 5,
  },
  {
    id: "code-gen",
    featureKey: "code_generation",
    title: "Generate Code",
    description: "AI code implementation",
    path: "/code-generation",
    icon: Code2,
    step: 6,
  },
  {
    id: "test-cases",
    featureKey: "test_cases",
    title: "Test Cases",
    description: "Generate test scenarios",
    path: "/test-cases",
    icon: TestTube,
    step: 7,
  },
  {
    id: "test-data",
    featureKey: "test_data",
    title: "Test Data",
    description: "Generate test datasets",
    path: "/test-data",
    icon: Database,
    step: 8,
  },
];

const agentItems = [
  { path: "/agent-chat", featureKey: "agent_jira", icon: Bot, title: "JIRA Agent", description: "Interactive JIRA assistant", testId: "link-agent-chat" },
  { path: "/agent-security", featureKey: "agent_security", icon: Shield, title: "Security Agent", description: "Web security assessment", testId: "link-agent-security" },
  { path: "/agent-unit-test", featureKey: "agent_unit_test", icon: FlaskConical, title: "Unit Test Agent", description: "Auto test generation", testId: "link-agent-unit-test" },
  { path: "/agent-web-test", featureKey: "agent_web_test", icon: Globe, title: "Web Test Agent", description: "Web app test cases", testId: "link-agent-web-test" },
];

interface AppSidebarProps {
  completedSteps?: string[];
}

const brdScopedPaths = new Set(["/brd", "/user-stories", "/test-cases", "/test-data"]);

export function AppSidebar({ completedSteps = [] }: AppSidebarProps) {
  const [location] = useLocation();
  const searchString = useSearch();
  const brdIdParam = new URLSearchParams(searchString).get("brd_id");
  const { user, isAdmin, hasPermission, logout } = useAuth();
  const { projects, currentProject, selectProject, isLoading: projectsLoading, isProjectLocked } = useProject();

  const getStepStatus = (step: WorkflowStep) => {
    if (completedSteps.includes(step.id)) return "completed";
    if (location === step.path) return "active";
    return "pending";
  };

  const visiblePrereqSteps = prerequisiteSteps.filter(s => hasPermission(s.featureKey));
  const visibleWorkflowSteps = workflowSteps.filter(s => hasPermission(s.featureKey));
  const visibleAgents = agentItems.filter(a => hasPermission(a.featureKey));

  const getStepHref = (step: WorkflowStep) => {
    if (brdIdParam && brdScopedPaths.has(step.path)) {
      return `${step.path}?brd_id=${brdIdParam}`;
    }
    return step.path;
  };

  const renderStepItem = (step: WorkflowStep, index: number, totalSteps: number) => {
    const status = getStepStatus(step);
    const isActive = location === step.path;
    const Icon = step.icon;

    return (
      <SidebarMenuItem key={step.id}>
        <SidebarMenuButton
          asChild
          className={cn(
            "group relative",
            isActive && "bg-sidebar-accent text-sidebar-accent-foreground"
          )}
        >
          <Link href={getStepHref(step)} data-testid={`link-step-${step.id}`}>
            <div className="flex items-center gap-3 w-full">
              <div className={cn(
                "flex h-8 w-8 shrink-0 items-center justify-center rounded-md border transition-colors",
                status === "completed" && "bg-success border-success text-success-foreground",
                status === "active" && "bg-primary border-primary text-primary-foreground",
                status === "pending" && "bg-muted border-border text-muted-foreground"
              )}>
                <Icon className="h-4 w-4" />
              </div>
              <div className="flex flex-col flex-1 min-w-0">
                <span className="text-sm font-medium truncate">{step.title}</span>
                <span className="text-xs text-muted-foreground truncate">{step.description}</span>
              </div>
              {status === "completed" && (
                <div className="flex h-5 w-5 items-center justify-center rounded-full bg-success text-success-foreground">
                  <svg className="h-3 w-3" viewBox="0 0 12 12" fill="none">
                    <path d="M2 6l3 3 5-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </div>
              )}
              {isActive && status !== "completed" && (
                <ChevronRight className="h-4 w-4 text-muted-foreground" />
              )}
            </div>
          </Link>
        </SidebarMenuButton>
        {index < totalSteps - 1 && (
          <div className="absolute left-[1.625rem] top-[3.25rem] h-4 w-0.5 bg-border" />
        )}
      </SidebarMenuItem>
    );
  };

  return (
    <Sidebar>
      <SidebarHeader className="border-b border-sidebar-border px-4 py-4">
        <Link href={isAdmin ? "/admin/projects" : "/"} className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary">
            <Sparkles className="h-5 w-5 text-primary-foreground" />
          </div>
          <div className="flex flex-col">
            <span className="text-base font-semibold text-sidebar-foreground">Defuse 2.O</span>
            <span className="text-xs text-muted-foreground">Modern SDLC acclerator </span>
          </div>
        </Link>
      </SidebarHeader>

      <SidebarContent className="px-2">
        {isAdmin ? (
          <>
            <SidebarGroup>
              <SidebarGroupLabel className="text-xs font-medium uppercase tracking-wider text-muted-foreground px-2">
                Administration
              </SidebarGroupLabel>
              <SidebarGroupContent>
                <SidebarMenu>
                  {[
                    { path: "/admin/projects", icon: FolderKanban, title: "Project Management", description: "Create & manage projects", testId: "link-admin-projects" },
                    { path: "/admin/users", icon: Users, title: "User Management", description: "Manage users & access", testId: "link-admin-users" },
                    { path: "/admin/rag-metrics", icon: BarChart3, title: "RAG Metrics", description: "BRD generation quality", testId: "link-admin-rag-metrics" },
                    { path: "/admin/prompts", icon: FileText, title: "Prompt Management", description: "Manage AI prompts", testId: "link-admin-prompts" },
                    { path: "/admin/settings", icon: Settings, title: "Settings", description: "System configuration", testId: "link-admin-settings" },
                  ].map((item) => {
                    const isActive = location === item.path;
                    const Icon = item.icon;
                    return (
                      <SidebarMenuItem key={item.path}>
                        <SidebarMenuButton
                          asChild
                          className={cn(
                            "group",
                            isActive && "bg-sidebar-accent text-sidebar-accent-foreground"
                          )}
                        >
                          <Link href={item.path} data-testid={item.testId}>
                            <div className="flex items-center gap-3 w-full">
                              <div className={cn(
                                "flex h-8 w-8 shrink-0 items-center justify-center rounded-md border transition-colors",
                                isActive
                                  ? "bg-primary border-primary text-primary-foreground"
                                  : "bg-muted border-border text-muted-foreground"
                              )}>
                                <Icon className="h-4 w-4" />
                              </div>
                              <div className="flex flex-col flex-1 min-w-0">
                                <span className="text-sm font-medium truncate">{item.title}</span>
                                <span className="text-xs text-muted-foreground truncate">{item.description}</span>
                              </div>
                              {isActive && (
                                <ChevronRight className="h-4 w-4 text-muted-foreground" />
                              )}
                            </div>
                          </Link>
                        </SidebarMenuButton>
                      </SidebarMenuItem>
                    );
                  })}
                </SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>
          </>
        ) : (
          <>
            <SidebarGroup>
              <SidebarGroupLabel className="text-xs font-medium uppercase tracking-wider text-muted-foreground px-2">
                Project
              </SidebarGroupLabel>
              <SidebarGroupContent>
                <div className="mx-2">
                  {projects.length === 0 ? (
                    <div className="p-3 rounded-md bg-sidebar-accent/50 border border-sidebar-border text-center">
                      <FolderOpen className="h-5 w-5 mx-auto text-muted-foreground mb-1" />
                      <p className="text-xs text-muted-foreground">No projects yet</p>
                    </div>
                  ) : isProjectLocked && currentProject ? (
                    <div className="flex items-center gap-2 px-3 py-2 rounded-md border border-sidebar-border bg-sidebar-accent/30" data-testid="locked-project-display">
                      <GitBranch className="h-3.5 w-3.5 shrink-0 text-primary" />
                      <span className="text-sm font-medium truncate">{currentProject.name}</span>
                      <Badge
                        variant="outline"
                        className={cn(
                          "text-[10px] px-1 py-0 ml-auto",
                          currentProject.status === "completed" && "bg-success/10 text-success border-success/30",
                          currentProject.status === "analyzing" && "bg-warning/10 text-warning border-warning/30",
                          currentProject.status === "error" && "bg-destructive/10 text-destructive border-destructive/30"
                        )}
                      >
                        {currentProject.status}
                      </Badge>
                    </div>
                  ) : (
                    <Select
                      value={currentProject?.id || ""}
                      onValueChange={selectProject}
                    >
                      <SelectTrigger className="w-full" data-testid="select-project">
                        <div className="flex items-center gap-2 truncate">
                          <GitBranch className="h-3.5 w-3.5 shrink-0 text-primary" />
                          <SelectValue placeholder="Select project" />
                        </div>
                      </SelectTrigger>
                      <SelectContent>
                        {projects.map((p) => (
                          <SelectItem key={p.id} value={p.id} data-testid={`option-project-${p.id}`}>
                            <div className="flex items-center gap-2">
                              <span className="truncate">{p.name}</span>
                              <Badge
                                variant="outline"
                                className={cn(
                                  "text-[10px] px-1 py-0",
                                  p.status === "completed" && "bg-success/10 text-success border-success/30",
                                  p.status === "analyzing" && "bg-warning/10 text-warning border-warning/30",
                                  p.status === "error" && "bg-destructive/10 text-destructive border-destructive/30"
                                )}
                              >
                                {p.status}
                              </Badge>
                            </div>
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                </div>
              </SidebarGroupContent>
            </SidebarGroup>

            {visiblePrereqSteps.length > 0 && (
              <SidebarGroup>
                <SidebarGroupLabel className="text-xs font-medium uppercase tracking-wider text-muted-foreground px-2">
                  Pre-requisite
                </SidebarGroupLabel>
                <SidebarGroupContent>
                  <SidebarMenu>
                    {visiblePrereqSteps.map((step, index) => renderStepItem(step, index, visiblePrereqSteps.length))}
                  </SidebarMenu>
                </SidebarGroupContent>
              </SidebarGroup>
            )}

            {visibleWorkflowSteps.length > 0 && (
              <SidebarGroup>
                <SidebarGroupLabel className="text-xs font-medium uppercase tracking-wider text-muted-foreground px-2">
                  Workflow
                </SidebarGroupLabel>
                <SidebarGroupContent>
                  <SidebarMenu>
                    {visibleWorkflowSteps.map((step, index) => renderStepItem(step, index, visibleWorkflowSteps.length))}
                  </SidebarMenu>
                </SidebarGroupContent>
              </SidebarGroup>
            )}

            {hasPermission("knowledge_base") && (
              <SidebarGroup>
                <SidebarGroupLabel className="text-xs font-medium uppercase tracking-wider text-muted-foreground px-2">
                  Knowledge Base
                </SidebarGroupLabel>
                <SidebarGroupContent>
                  <SidebarMenu>
                    <SidebarMenuItem>
                      <SidebarMenuButton
                        asChild
                        className={cn(
                          "group",
                          location === "/knowledge-base" && "bg-sidebar-accent text-sidebar-accent-foreground"
                        )}
                      >
                        <Link href="/knowledge-base" data-testid="link-knowledge-base">
                          <div className="flex items-center gap-3 w-full">
                            <div className={cn(
                              "flex h-8 w-8 shrink-0 items-center justify-center rounded-md border transition-colors",
                              location === "/knowledge-base" 
                                ? "bg-primary border-primary text-primary-foreground"
                                : "bg-muted border-border text-muted-foreground"
                            )}>
                              <Library className="h-4 w-4" />
                            </div>
                            <div className="flex flex-col flex-1 min-w-0">
                              <span className="text-sm font-medium truncate">Documents</span>
                              <span className="text-xs text-muted-foreground truncate">Upload & manage docs</span>
                            </div>
                            {location === "/knowledge-base" && (
                              <ChevronRight className="h-4 w-4 text-muted-foreground" />
                            )}
                          </div>
                        </Link>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  </SidebarMenu>
                </SidebarGroupContent>
              </SidebarGroup>
            )}

            <SidebarGroup>
              <SidebarGroupLabel className="text-xs font-medium uppercase tracking-wider text-muted-foreground px-2">
                History
              </SidebarGroupLabel>
              <SidebarGroupContent>
                <SidebarMenu>
                  <SidebarMenuItem>
                    <SidebarMenuButton
                      asChild
                      className={cn(
                        "group",
                        location === "/generation-history" && "bg-sidebar-accent text-sidebar-accent-foreground"
                      )}
                    >
                      <Link href="/generation-history" data-testid="link-generation-history">
                        <div className="flex items-center gap-3 w-full">
                          <div className={cn(
                            "flex h-8 w-8 shrink-0 items-center justify-center rounded-md border transition-colors",
                            location === "/generation-history" 
                              ? "bg-primary border-primary text-primary-foreground"
                              : "bg-muted border-border text-muted-foreground"
                          )}>
                            <History className="h-4 w-4" />
                          </div>
                          <div className="flex flex-col flex-1 min-w-0">
                            <span className="text-sm font-medium truncate">Generation History</span>
                            <span className="text-xs text-muted-foreground truncate">All artifacts by feature</span>
                          </div>
                          {location === "/generation-history" && (
                            <ChevronRight className="h-4 w-4 text-muted-foreground" />
                          )}
                        </div>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                </SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>

            {visibleAgents.length > 0 && (
              <SidebarGroup>
                <SidebarGroupLabel className="text-xs font-medium uppercase tracking-wider text-muted-foreground px-2">
                  AI Agents
                </SidebarGroupLabel>
                <SidebarGroupContent>
                  <SidebarMenu>
                    {visibleAgents.map((agent) => {
                      const isActive = location === agent.path;
                      const Icon = agent.icon;
                      return (
                        <SidebarMenuItem key={agent.path}>
                          <SidebarMenuButton
                            asChild
                            className={cn(
                              "group",
                              isActive && "bg-sidebar-accent text-sidebar-accent-foreground"
                            )}
                          >
                            <Link href={agent.path} data-testid={agent.testId}>
                              <div className="flex items-center gap-3 w-full">
                                <div className={cn(
                                  "flex h-8 w-8 shrink-0 items-center justify-center rounded-md border transition-colors",
                                  isActive
                                    ? "bg-primary border-primary text-primary-foreground"
                                    : "bg-muted border-border text-muted-foreground"
                                )}>
                                  <Icon className="h-4 w-4" />
                                </div>
                                <div className="flex flex-col flex-1 min-w-0">
                                  <span className="text-sm font-medium truncate">{agent.title}</span>
                                  <span className="text-xs text-muted-foreground truncate">{agent.description}</span>
                                </div>
                                {isActive && (
                                  <ChevronRight className="h-4 w-4 text-muted-foreground" />
                                )}
                              </div>
                            </Link>
                          </SidebarMenuButton>
                        </SidebarMenuItem>
                      );
                    })}
                  </SidebarMenu>
                </SidebarGroupContent>
              </SidebarGroup>
            )}
          </>
        )}
      </SidebarContent>

      <SidebarFooter className="border-t border-sidebar-border px-3 py-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-muted">
              <User className="h-3.5 w-3.5 text-muted-foreground" />
            </div>
            <div className="min-w-0">
              <p className="text-sm font-medium truncate">{user?.username}</p>
              <p className="text-xs text-muted-foreground truncate">{user?.role}</p>
            </div>
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={logout}
            title="Sign out"
            data-testid="button-logout"
          >
            <LogOut className="h-4 w-4" />
          </Button>
        </div>
      </SidebarFooter>
    </Sidebar>
  );
}
