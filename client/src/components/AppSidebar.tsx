import { useLocation, Link } from "wouter";
import {
  GitBranch,
  FileText,
  ClipboardList,
  FileCheck,
  TestTube,
  Database,
  Home,
  ChevronRight,
  Sparkles,
  Bookmark,
  Library,
  Upload,
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
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

interface WorkflowStep {
  id: string;
  title: string;
  description: string;
  path: string;
  icon: React.ElementType;
  step: number;
}

const workflowSteps: WorkflowStep[] = [
  {
    id: "analyze",
    title: "Analyze Repository",
    description: "Connect and analyze GitHub repo",
    path: "/",
    icon: GitBranch,
    step: 1,
  },
  {
    id: "document",
    title: "Documentation",
    description: "View generated docs",
    path: "/documentation",
    icon: FileText,
    step: 2,
  },
  {
    id: "requirements",
    title: "Feature Request",
    description: "Input new requirements",
    path: "/requirements",
    icon: ClipboardList,
    step: 3,
  },
  {
    id: "brd",
    title: "Generate BRD",
    description: "Create business requirements",
    path: "/brd",
    icon: FileCheck,
    step: 4,
  },
  {
    id: "user-stories",
    title: "User Stories",
    description: "Generate stories for JIRA",
    path: "/user-stories",
    icon: Bookmark,
    step: 5,
  },
  {
    id: "test-cases",
    title: "Test Cases",
    description: "Generate test scenarios",
    path: "/test-cases",
    icon: TestTube,
    step: 6,
  },
  {
    id: "test-data",
    title: "Test Data",
    description: "Generate test datasets",
    path: "/test-data",
    icon: Database,
    step: 7,
  },
];

interface AppSidebarProps {
  currentProject?: { name: string; status: string } | null;
  completedSteps?: string[];
}

export function AppSidebar({ currentProject, completedSteps = [] }: AppSidebarProps) {
  const [location] = useLocation();

  const getStepStatus = (step: WorkflowStep) => {
    if (completedSteps.includes(step.id)) return "completed";
    if (location === step.path) return "active";
    return "pending";
  };

  return (
    <Sidebar>
      <SidebarHeader className="border-b border-sidebar-border px-4 py-4">
        <Link href="/" className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary">
            <Sparkles className="h-5 w-5 text-primary-foreground" />
          </div>
          <div className="flex flex-col">
            <span className="text-base font-semibold text-sidebar-foreground">DocuGen AI</span>
            <span className="text-xs text-muted-foreground">Documentation Platform</span>
          </div>
        </Link>
      </SidebarHeader>

      <SidebarContent className="px-2">
        {currentProject && (
          <SidebarGroup>
            <SidebarGroupLabel className="text-xs font-medium uppercase tracking-wider text-muted-foreground px-2">
              Current Project
            </SidebarGroupLabel>
            <SidebarGroupContent>
              <div className="mx-2 p-3 rounded-md bg-sidebar-accent/50 border border-sidebar-border">
                <div className="flex items-center gap-2">
                  <GitBranch className="h-4 w-4 text-primary" />
                  <span className="font-medium text-sm truncate">{currentProject.name}</span>
                </div>
                <Badge 
                  variant="outline" 
                  className={cn(
                    "mt-2 text-xs",
                    currentProject.status === "completed" && "bg-success/10 text-success border-success/30",
                    currentProject.status === "analyzing" && "bg-warning/10 text-warning border-warning/30",
                    currentProject.status === "error" && "bg-destructive/10 text-destructive border-destructive/30"
                  )}
                >
                  {currentProject.status}
                </Badge>
              </div>
            </SidebarGroupContent>
          </SidebarGroup>
        )}

        <SidebarGroup>
          <SidebarGroupLabel className="text-xs font-medium uppercase tracking-wider text-muted-foreground px-2">
            Workflow
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {workflowSteps.map((step, index) => {
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
                      <Link href={step.path} data-testid={`link-step-${step.id}`}>
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
                    {index < workflowSteps.length - 1 && (
                      <div className="absolute left-[1.625rem] top-[3.25rem] h-4 w-0.5 bg-border" />
                    )}
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

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
      </SidebarContent>

      <SidebarFooter className="border-t border-sidebar-border px-4 py-3">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Sparkles className="h-3 w-3" />
          <span>Powered by AI</span>
        </div>
      </SidebarFooter>
    </Sidebar>
  );
}
