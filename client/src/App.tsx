import { Switch, Route, useLocation, Redirect } from "wouter";
import { queryClient } from "./lib/queryClient";
import { QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { SidebarProvider, SidebarTrigger, SidebarInset } from "@/components/ui/sidebar";
import { ThemeProvider } from "@/components/ThemeProvider";
import { ThemeToggle } from "@/components/ThemeToggle";
import { AppSidebar } from "@/components/AppSidebar";
import { SessionContext, useSessionProvider } from "@/hooks/useSession";
import { AuthProvider, useAuth } from "@/hooks/useAuth";
import { ProjectProvider, useProject } from "@/hooks/useProject";
import { Loader2 } from "lucide-react";
import NotFound from "@/pages/not-found";
import LoginPage from "@/pages/LoginPage";
import AdminPage from "@/pages/AdminPage";
import AnalyzePage from "@/pages/AnalyzePage";
import DocumentationPage from "@/pages/DocumentationPage";
import RequirementsPage from "@/pages/RequirementsPage";
import BRDPage from "@/pages/BRDPage";
import UserStoriesPage from "@/pages/UserStoriesPage";
import TestCasesPage from "@/pages/TestCasesPage";
import TestDataPage from "@/pages/TestDataPage";
import KnowledgeBasePage from "@/pages/KnowledgeBasePage";
import AgentChatPage from "@/pages/AgentChatPage";
import SecurityAgentPage from "@/pages/SecurityAgentPage";
import UnitTestAgentPage from "@/pages/UnitTestAgentPage";
import WebTestAgentPage from "@/pages/WebTestAgentPage";
import CodeGenerationPage from "@/pages/CodeGenerationPage";
import GenerationHistoryPage from "@/pages/GenerationHistoryPage";

const featureRouteMap: Record<string, string> = {
  "/": "analyze",
  "/documentation": "documentation",
  "/requirements": "requirements",
  "/brd": "brd",
  "/user-stories": "user_stories",
  "/code-generation": "code_generation",
  "/test-cases": "test_cases",
  "/test-data": "test_data",
  "/knowledge-base": "knowledge_base",
  "/agent-chat": "agent_jira",
  "/agent-security": "agent_security",
  "/agent-unit-test": "agent_unit_test",
  "/agent-web-test": "agent_web_test",
};

function ProtectedRoute({ component: Component, featureKey }: { component: React.ComponentType; featureKey?: string }) {
  const { hasPermission } = useAuth();
  if (featureKey && !hasPermission(featureKey)) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center space-y-2">
          <h2 className="text-lg font-semibold">Access Denied</h2>
          <p className="text-sm text-muted-foreground">You don't have permission to access this feature.</p>
          <p className="text-xs text-muted-foreground">Contact your administrator for access.</p>
        </div>
      </div>
    );
  }
  return <Component />;
}

function AdminRoute({ initialTab }: { initialTab: string }) {
  const { isAdmin } = useAuth();
  if (!isAdmin) return <Redirect to="/" />;
  return <AdminPage initialTab={initialTab} />;
}

function Router() {
  const { isAdmin } = useAuth();

  return (
    <Switch>
      <Route path="/">{() => isAdmin ? <Redirect to="/admin/projects" /> : <ProtectedRoute component={AnalyzePage} featureKey="analyze" />}</Route>
      <Route path="/documentation">{() => <ProtectedRoute component={DocumentationPage} featureKey="documentation" />}</Route>
      <Route path="/requirements">{() => <ProtectedRoute component={RequirementsPage} featureKey="requirements" />}</Route>
      <Route path="/brd">{() => <ProtectedRoute component={BRDPage} featureKey="brd" />}</Route>
      <Route path="/user-stories">{() => <ProtectedRoute component={UserStoriesPage} featureKey="user_stories" />}</Route>
      <Route path="/code-generation">{() => <ProtectedRoute component={CodeGenerationPage} featureKey="code_generation" />}</Route>
      <Route path="/test-cases">{() => <ProtectedRoute component={TestCasesPage} featureKey="test_cases" />}</Route>
      <Route path="/test-data">{() => <ProtectedRoute component={TestDataPage} featureKey="test_data" />}</Route>
      <Route path="/knowledge-base">{() => <ProtectedRoute component={KnowledgeBasePage} featureKey="knowledge_base" />}</Route>
      <Route path="/generation-history">{() => <ProtectedRoute component={GenerationHistoryPage} />}</Route>
      <Route path="/agent-chat">{() => isAdmin ? <ProtectedRoute component={AgentChatPage} featureKey="agent_jira" /> : <Redirect to="/" />}</Route>
      <Route path="/agent-security">{() => isAdmin ? <ProtectedRoute component={SecurityAgentPage} featureKey="agent_security" /> : <Redirect to="/" />}</Route>
      <Route path="/agent-unit-test">{() => isAdmin ? <ProtectedRoute component={UnitTestAgentPage} featureKey="agent_unit_test" /> : <Redirect to="/" />}</Route>
      <Route path="/agent-web-test">{() => isAdmin ? <ProtectedRoute component={WebTestAgentPage} featureKey="agent_web_test" /> : <Redirect to="/" />}</Route>
      <Route path="/admin/projects">{() => <AdminRoute initialTab="projects" />}</Route>
      <Route path="/admin/users">{() => <AdminRoute initialTab="users" />}</Route>
      <Route path="/admin/rag-metrics">{() => <AdminRoute initialTab="rag-metrics" />}</Route>
      <Route path="/admin/prompts">{() => <AdminRoute initialTab="prompts" />}</Route>
      <Route path="/admin/settings">{() => <AdminRoute initialTab="settings" />}</Route>
      <Route path="/admin">{() => <Redirect to="/admin/projects" />}</Route>
      <Route component={NotFound} />
    </Switch>
  );
}

function AppLayout() {
  const { user } = useAuth();

  const sidebarStyle = {
    "--sidebar-width": "18rem",
    "--sidebar-width-icon": "4rem",
  };

  return (
    <SidebarProvider style={sidebarStyle as React.CSSProperties}>
      <div className="flex h-screen w-full overflow-hidden">
        <AppSidebar completedSteps={[]} />
        <SidebarInset className="flex flex-col flex-1 overflow-hidden">
          <header className="flex items-center justify-between h-14 shrink-0 gap-2 px-4 border-b border-border bg-background">
            <SidebarTrigger data-testid="button-sidebar-toggle" />
            <div className="flex items-center gap-2">
              {user && (
                <span className="text-xs text-muted-foreground" data-testid="text-user-info">
                  {user.username} ({user.role})
                </span>
              )}
              <ThemeToggle />
            </div>
          </header>
          <main className="flex-1 overflow-hidden">
            <Router />
          </main>
        </SidebarInset>
      </div>
    </SidebarProvider>
  );
}

function SessionWrapper({ children }: { children: React.ReactNode }) {
  const sessionValue = useSessionProvider();
  return (
    <SessionContext.Provider value={sessionValue}>
      {children}
    </SessionContext.Provider>
  );
}

function AuthGate() {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <LoginPage />;
  }

  return (
    <ProjectProvider>
      <SessionWrapper>
        <AppLayout />
      </SessionWrapper>
    </ProjectProvider>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <TooltipProvider>
          <AuthProvider>
            <AuthGate />
          </AuthProvider>
          <Toaster />
        </TooltipProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}

export default App;
