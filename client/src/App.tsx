import { Switch, Route } from "wouter";
import { useQuery } from "@tanstack/react-query";
import { queryClient, hydrateFromLocalStorage } from "./lib/queryClient";
import { QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { SidebarProvider, SidebarTrigger, SidebarInset } from "@/components/ui/sidebar";
import { ThemeProvider } from "@/components/ThemeProvider";
import { ThemeToggle } from "@/components/ThemeToggle";
import { AppSidebar } from "@/components/AppSidebar";
import { SessionContext, useSessionProvider } from "@/hooks/useSession";
import NotFound from "@/pages/not-found";
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
import type { Project } from "@shared/schema";

hydrateFromLocalStorage();

function Router() {
  return (
    <Switch>
      <Route path="/" component={AnalyzePage} />
      <Route path="/documentation" component={DocumentationPage} />
      <Route path="/requirements" component={RequirementsPage} />
      <Route path="/brd" component={BRDPage} />
      <Route path="/user-stories" component={UserStoriesPage} />
      <Route path="/test-cases" component={TestCasesPage} />
      <Route path="/test-data" component={TestDataPage} />
      <Route path="/knowledge-base" component={KnowledgeBasePage} />
      <Route path="/agent-chat" component={AgentChatPage} />
      <Route path="/agent-security" component={SecurityAgentPage} />
      <Route path="/agent-unit-test" component={UnitTestAgentPage} />
      <Route path="/agent-web-test" component={WebTestAgentPage} />
      <Route component={NotFound} />
    </Switch>
  );
}

function AppLayout() {
  const { data: projects } = useQuery<Project[]>({
    queryKey: ["/api/projects"],
  });
  
  const currentProject = projects && projects.length > 0 ? projects[0] : null;

  const sidebarStyle = {
    "--sidebar-width": "18rem",
    "--sidebar-width-icon": "4rem",
  };

  return (
    <SidebarProvider style={sidebarStyle as React.CSSProperties}>
      <div className="flex h-screen w-full overflow-hidden">
        <AppSidebar 
          currentProject={currentProject ? { name: currentProject.name, status: currentProject.status } : null}
          completedSteps={[]}
        />
        <SidebarInset className="flex flex-col flex-1 overflow-hidden">
          <header className="flex items-center justify-between h-14 shrink-0 gap-2 px-4 border-b border-border bg-background">
            <SidebarTrigger data-testid="button-sidebar-toggle" />
            <ThemeToggle />
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

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <TooltipProvider>
          <SessionWrapper>
            <AppLayout />
          </SessionWrapper>
          <Toaster />
        </TooltipProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}

export default App;
