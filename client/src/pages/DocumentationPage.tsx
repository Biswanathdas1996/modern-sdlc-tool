import { useState, useEffect } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { queryClient, apiRequest } from "@/lib/queryClient";
import { Link } from "wouter";
import { FileText, ChevronRight, Search, Download, Layers, Code, Database, Settings, Package, ChevronDown, GitBranch, Loader2, RefreshCw, Table2, Key, Link2, Trash2, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { WorkflowHeader } from "@/components/WorkflowHeader";
import { DocumentPreview } from "@/components/DocumentPreview";
import { CodeBlock } from "@/components/CodeBlock";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { EmptyState } from "@/components/EmptyState";
import { MermaidDiagram } from "@/components/MermaidDiagram";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import type { Documentation, RepoAnalysis, BPMNDiagram, DatabaseSchemaInfo } from "@shared/schema";
import { useToast } from "@/hooks/use-toast";
import { useSession } from "@/hooks/useSession";

const workflowSteps = [
  { id: "analyze", label: "Analyze", completed: true, active: false },
  { id: "document", label: "Document", completed: false, active: true },
  { id: "requirements", label: "Requirements", completed: false, active: false },
  { id: "brd", label: "BRD", completed: false, active: false },
  { id: "user-stories", label: "Stories", completed: false, active: false },
  { id: "test-cases", label: "Tests", completed: false, active: false },
  { id: "test-data", label: "Data", completed: false, active: false },
];

interface TocItem {
  id: string;
  title: string;
  level: number;
  children?: TocItem[];
}

export default function DocumentationPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [activeSection, setActiveSection] = useState("overview");
  const [connectionString, setConnectionString] = useState("");
  const { toast } = useToast();
  const { saveSessionArtifact } = useSession();

  const handleSectionSelect = (sectionId: string) => {
    setActiveSection(sectionId);
    const element = document.getElementById(sectionId);
    if (element) {
      element.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  const { data: analysis, isLoading: analysisLoading } = useQuery<RepoAnalysis>({
    queryKey: ["/api/analysis/current"],
  });

  const { data: documentation, isLoading: docLoading } = useQuery<Documentation>({
    queryKey: ["/api/documentation/current"],
  });

  const { data: bpmnDiagrams, isLoading: bpmnLoading } = useQuery<BPMNDiagram>({
    queryKey: ["/api/bpmn/current"],
    enabled: !!documentation,
  });

  const regenerateBpmnMutation = useMutation({
    mutationFn: async () => {
      const response = await apiRequest("POST", "/api/bpmn/regenerate");
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/bpmn/current"] });
    },
  });

  const { data: databaseSchema, isLoading: dbSchemaLoading } = useQuery<DatabaseSchemaInfo | null>({
    queryKey: ["/api/database-schema/current"],
    enabled: !!documentation,
  });

  const connectDatabaseMutation = useMutation({
    mutationFn: async (connString: string) => {
      const response = await apiRequest("POST", "/api/database-schema/connect", {
        connectionString: connString,
      });
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/database-schema/current"] });
      setConnectionString("");
      toast({
        title: "Database Connected",
        description: "Database schema has been retrieved successfully.",
      });
    },
    onError: (error: any) => {
      toast({
        title: "Connection Failed",
        description: error.message || "Failed to connect to database",
        variant: "destructive",
      });
    },
  });

  const deleteDatabaseSchemaMutation = useMutation({
    mutationFn: async () => {
      await apiRequest("DELETE", "/api/database-schema/current");
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/database-schema/current"] });
      toast({
        title: "Schema Removed",
        description: "Database schema has been removed from this project.",
      });
    },
  });

  useEffect(() => {
    if (documentation) saveSessionArtifact("documentation", documentation);
  }, [documentation, saveSessionArtifact]);

  useEffect(() => {
    if (analysis) saveSessionArtifact("analysis", analysis);
  }, [analysis, saveSessionArtifact]);

  useEffect(() => {
    if (bpmnDiagrams) saveSessionArtifact("bpmn", bpmnDiagrams);
  }, [bpmnDiagrams, saveSessionArtifact]);

  useEffect(() => {
    if (databaseSchema) saveSessionArtifact("databaseSchema", databaseSchema);
  }, [databaseSchema, saveSessionArtifact]);

  const isLoading = analysisLoading || docLoading;

  const tocItems: TocItem[] = [
    { id: "overview", title: "Overview", level: 0 },
    { id: "architecture", title: "Architecture", level: 0 },
    {
      id: "tech-stack",
      title: "Tech Stack",
      level: 0,
      children: [
        { id: "languages", title: "Languages", level: 1 },
        { id: "frameworks", title: "Frameworks", level: 1 },
        { id: "databases", title: "Databases", level: 1 },
        { id: "tools", title: "Tools", level: 1 },
      ],
    },
    { id: "features", title: "Features", level: 0 },
    { id: "user-journeys", title: "Business Flow", level: 0 },
    { id: "database-schema", title: "Database Schema", level: 0 },
    { id: "code-patterns", title: "Code Patterns", level: 0 },
    { id: "testing", title: "Testing", level: 0 },
  ];

  const mockAnalysis: RepoAnalysis = analysis || {
    id: "1",
    projectId: "1",
    summary: "A modern full-stack web application built with React and Node.js, featuring a robust API layer and comprehensive test coverage.",
    architecture: "The application follows a clean architecture pattern with clear separation between presentation, business logic, and data access layers. The frontend uses React with TypeScript, while the backend is built on Express.js with PostgreSQL for data persistence.",
    features: [
      {
        name: "User Authentication",
        description: "Complete user authentication system with JWT tokens, password hashing, and session management.",
        files: ["src/auth/login.ts", "src/auth/register.ts", "src/middleware/auth.ts"],
      },
      {
        name: "API Gateway",
        description: "RESTful API endpoints for data operations with validation and error handling.",
        files: ["src/routes/api.ts", "src/controllers/*.ts"],
      },
      {
        name: "Database Layer",
        description: "ORM-based database operations with migrations and seeding support.",
        files: ["src/models/*.ts", "src/migrations/*.ts"],
      },
    ],
    techStack: {
      languages: ["TypeScript", "JavaScript", "SQL"],
      frameworks: ["React", "Express.js", "Node.js"],
      databases: ["PostgreSQL", "Redis"],
      tools: ["Docker", "GitHub Actions", "ESLint", "Prettier"],
    },
    testingFramework: "Jest with React Testing Library",
    codePatterns: [
      "Repository Pattern for data access",
      "Factory Pattern for object creation",
      "Observer Pattern for event handling",
      "Singleton Pattern for service instances",
    ],
    createdAt: new Date().toISOString(),
  };

  const handleExport = () => {
    const content = JSON.stringify(mockAnalysis, null, 2);
    const blob = new Blob([content], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "documentation.json";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="flex flex-col h-full">
      <WorkflowHeader
        steps={workflowSteps}
        title="Generated Documentation"
        description="Comprehensive technical documentation extracted from your repository analysis."
      />

      {isLoading ? (
        <div className="flex-1 flex items-center justify-center">
          <LoadingSpinner size="lg" text="Loading documentation..." />
        </div>
      ) : !documentation ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center space-y-4 max-w-md">
            <FileText className="h-16 w-16 mx-auto text-muted-foreground/50" />
            <h2 className="text-xl font-semibold text-foreground">No Documentation Yet</h2>
            <p className="text-muted-foreground">
              Start by analyzing a GitHub repository to generate technical documentation.
              Once analyzed, you can also connect your database schema here.
            </p>
            <Button asChild>
              <Link to="/">
                Analyze Repository
              </Link>
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex-1 flex overflow-hidden min-h-0">
          {/* Sidebar TOC */}
          <aside className="w-64 border-r border-border bg-card/50 flex flex-col shrink-0 hidden md:flex">
            <div className="p-4 border-b border-border">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  type="search"
                  placeholder="Search docs..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-9"
                  data-testid="input-search-docs"
                />
              </div>
            </div>
            <ScrollArea className="flex-1">
              <nav className="p-4 space-y-1">
                {tocItems.map((item) => (
                  <TocItemComponent
                    key={item.id}
                    item={item}
                    activeSection={activeSection}
                    onSelect={handleSectionSelect}
                  />
                ))}
              </nav>
            </ScrollArea>
          </aside>

          {/* Main Content */}
          <main className="flex-1 overflow-y-auto overflow-x-hidden min-w-0">
            <div className="p-6 max-w-4xl mx-auto space-y-8">
              {/* Overview Section */}
              <section id="overview" className="space-y-4 animate-fade-in">
                <div className="flex items-center justify-between gap-4 flex-wrap">
                  <h2 className="text-2xl font-bold text-foreground flex items-center gap-2">
                    <FileText className="h-6 w-6 text-primary" />
                    Overview
                  </h2>
                  <Button variant="outline" onClick={handleExport} data-testid="button-export-docs">
                    <Download className="h-4 w-4 mr-2" />
                    Export
                  </Button>
                </div>
                <Card>
                  <CardContent className="pt-6">
                    <p className="text-foreground leading-relaxed">{mockAnalysis.summary}</p>
                  </CardContent>
                </Card>
              </section>

              {/* Architecture Section */}
              <section id="architecture" className="space-y-4 animate-fade-in">
                <h2 className="text-2xl font-bold text-foreground flex items-center gap-2">
                  <Layers className="h-6 w-6 text-accent" />
                  Architecture
                </h2>
                <Card>
                  <CardContent className="pt-6">
                    <p className="text-foreground leading-relaxed">{mockAnalysis.architecture}</p>
                  </CardContent>
                </Card>
              </section>

              {/* Tech Stack Section */}
              <section id="tech-stack" className="space-y-4 animate-fade-in">
                <h2 className="text-2xl font-bold text-foreground flex items-center gap-2">
                  <Package className="h-6 w-6 text-success" />
                  Tech Stack
                </h2>
                <div className="grid md:grid-cols-2 gap-4">
                  <Card id="languages">
                    <CardHeader className="pb-3">
                      <CardTitle className="text-base flex items-center gap-2">
                        <Code className="h-4 w-4 text-primary" />
                        Languages
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="flex flex-wrap gap-2">
                        {mockAnalysis.techStack.languages.map((lang) => (
                          <Badge key={lang} variant="secondary">
                            {lang}
                          </Badge>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                  <Card id="frameworks">
                    <CardHeader className="pb-3">
                      <CardTitle className="text-base flex items-center gap-2">
                        <Layers className="h-4 w-4 text-accent" />
                        Frameworks
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="flex flex-wrap gap-2">
                        {mockAnalysis.techStack.frameworks.map((fw) => (
                          <Badge key={fw} variant="secondary">
                            {fw}
                          </Badge>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                  <Card id="databases">
                    <CardHeader className="pb-3">
                      <CardTitle className="text-base flex items-center gap-2">
                        <Database className="h-4 w-4 text-warning" />
                        Databases
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="flex flex-wrap gap-2">
                        {mockAnalysis.techStack.databases.map((db) => (
                          <Badge key={db} variant="secondary">
                            {db}
                          </Badge>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                  <Card id="tools">
                    <CardHeader className="pb-3">
                      <CardTitle className="text-base flex items-center gap-2">
                        <Settings className="h-4 w-4 text-muted-foreground" />
                        Tools
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="flex flex-wrap gap-2">
                        {mockAnalysis.techStack.tools.map((tool) => (
                          <Badge key={tool} variant="secondary">
                            {tool}
                          </Badge>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                </div>
              </section>

              {/* Features Section */}
              <section id="features" className="space-y-4 animate-fade-in">
                <h2 className="text-2xl font-bold text-foreground">Features</h2>
                <div className="space-y-4">
                  {mockAnalysis.features.map((feature, index) => (
                    <Card key={index}>
                      <CardHeader className="pb-3">
                        <CardTitle className="text-base">{feature.name}</CardTitle>
                      </CardHeader>
                      <CardContent className="space-y-3">
                        <p className="text-muted-foreground">{feature.description}</p>
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-foreground mb-2">Related Files:</p>
                          <div className="flex flex-wrap gap-2">
                            {feature.files.map((file) => (
                              <Badge key={file} variant="outline" className="font-mono text-xs break-all">
                                {file}
                              </Badge>
                            ))}
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              </section>

              {/* Business Flow Diagram Section */}
              <section id="user-journeys" className="space-y-4 animate-fade-in">
                <h2 className="text-2xl font-bold text-foreground flex items-center gap-2">
                  <GitBranch className="h-6 w-6 text-primary" />
                  Business Flow
                </h2>
                <p className="text-muted-foreground">
                  Complete end-to-end business process flow showing how users progress through the entire application.
                </p>
                
                {bpmnLoading ? (
                  <Card>
                    <CardContent className="pt-6 flex items-center justify-center py-12">
                      <div className="flex items-center gap-3 text-muted-foreground">
                        <Loader2 className="h-5 w-5 animate-spin" />
                        <span>Generating business flow diagram...</span>
                      </div>
                    </CardContent>
                  </Card>
                ) : bpmnDiagrams?.diagrams && bpmnDiagrams.diagrams.length > 0 ? (
                  <Card data-testid="card-bpmn-diagram">
                    <CardHeader className="pb-3">
                      <div className="flex items-center justify-between gap-2">
                        <CardTitle className="text-lg flex items-center gap-2">
                          <Badge className="bg-primary/10 text-primary border-primary/30">
                            BPMN
                          </Badge>
                          {bpmnDiagrams.diagrams[0].featureName}
                        </CardTitle>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => regenerateBpmnMutation.mutate()}
                          disabled={regenerateBpmnMutation.isPending}
                          data-testid="button-regenerate-bpmn"
                        >
                          {regenerateBpmnMutation.isPending ? (
                            <Loader2 className="h-4 w-4 animate-spin mr-2" />
                          ) : (
                            <RefreshCw className="h-4 w-4 mr-2" />
                          )}
                          Regenerate
                        </Button>
                      </div>
                      <CardDescription>{bpmnDiagrams.diagrams[0].description}</CardDescription>
                    </CardHeader>
                    <CardContent>
                      <div className="bg-muted/30 rounded-lg p-6 overflow-x-auto max-w-full">
                        <MermaidDiagram 
                          chart={bpmnDiagrams.diagrams[0].mermaidCode} 
                          className="min-h-[400px]"
                        />
                      </div>
                    </CardContent>
                  </Card>
                ) : (
                  <Card>
                    <CardContent className="pt-6">
                      <p className="text-muted-foreground text-center py-4">
                        No business flow diagram available yet. It will be generated automatically after analyzing a repository.
                      </p>
                    </CardContent>
                  </Card>
                )}
              </section>

              {/* Database Schema Section */}
              <section id="database-schema" className="space-y-4 animate-fade-in">
                <h2 className="text-2xl font-bold text-foreground flex items-center gap-2">
                  <Table2 className="h-6 w-6 text-warning" />
                  Database Schema
                </h2>
                <p className="text-muted-foreground">
                  Connect to your PostgreSQL database to include schema information in generated BRDs, user stories, and prompts.
                </p>

                {!databaseSchema ? (
                  <Card>
                    <CardContent className="pt-6">
                      <div className="space-y-4">
                        <div className="space-y-2">
                          <label className="text-sm font-medium text-foreground">
                            PostgreSQL Connection String
                          </label>
                          <div className="flex gap-2">
                            <Input
                              type="password"
                              placeholder="postgresql://user:password@host:port/database?sslmode=require"
                              value={connectionString}
                              onChange={(e) => setConnectionString(e.target.value)}
                              className="flex-1 font-mono text-sm"
                              data-testid="input-connection-string"
                            />
                            <Button
                              onClick={() => connectDatabaseMutation.mutate(connectionString)}
                              disabled={!connectionString || connectDatabaseMutation.isPending}
                              data-testid="button-connect-database"
                            >
                              {connectDatabaseMutation.isPending ? (
                                <Loader2 className="h-4 w-4 animate-spin mr-2" />
                              ) : (
                                <Database className="h-4 w-4 mr-2" />
                              )}
                              Connect
                            </Button>
                          </div>
                          <p className="text-xs text-muted-foreground">
                            Paste your PostgreSQL connection string. The password will be masked after connection.
                          </p>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                ) : (
                  <Card data-testid="card-database-schema">
                    <CardHeader className="pb-3">
                      <div className="flex items-center justify-between gap-2">
                        <CardTitle className="text-lg flex items-center gap-2">
                          <CheckCircle2 className="h-5 w-5 text-success" />
                          {databaseSchema.databaseName}
                        </CardTitle>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => deleteDatabaseSchemaMutation.mutate()}
                          disabled={deleteDatabaseSchemaMutation.isPending}
                          data-testid="button-remove-schema"
                        >
                          {deleteDatabaseSchemaMutation.isPending ? (
                            <Loader2 className="h-4 w-4 animate-spin mr-2" />
                          ) : (
                            <Trash2 className="h-4 w-4 mr-2" />
                          )}
                          Remove
                        </Button>
                      </div>
                      <CardDescription>
                        {databaseSchema.tables.length} tables connected
                      </CardDescription>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-4">
                        {databaseSchema.tables.map((table) => (
                          <Collapsible key={table.name} defaultOpen={false}>
                            <CollapsibleTrigger className="flex items-center justify-between w-full p-3 bg-muted/50 rounded-lg hover-elevate">
                              <div className="flex items-center gap-2">
                                <Table2 className="h-4 w-4 text-primary" />
                                <span className="font-mono font-medium">{table.name}</span>
                                <Badge variant="secondary" className="text-xs">
                                  {table.columns.length} columns
                                </Badge>
                                {table.rowCount !== undefined && (
                                  <Badge variant="outline" className="text-xs">
                                    {table.rowCount.toLocaleString()} rows
                                  </Badge>
                                )}
                              </div>
                              <ChevronDown className="h-4 w-4 text-muted-foreground" />
                            </CollapsibleTrigger>
                            <CollapsibleContent className="pt-2">
                              <div className="border rounded-lg overflow-x-auto">
                                <table className="w-full text-sm min-w-[500px]">
                                  <thead className="bg-muted/50">
                                    <tr>
                                      <th className="text-left p-2 font-medium">Column</th>
                                      <th className="text-left p-2 font-medium">Type</th>
                                      <th className="text-left p-2 font-medium">Nullable</th>
                                      <th className="text-left p-2 font-medium">Keys</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {table.columns.map((col) => (
                                      <tr key={col.name} className="border-t">
                                        <td className="p-2 font-mono text-xs">{col.name}</td>
                                        <td className="p-2">
                                          <Badge variant="secondary" className="font-mono text-xs">
                                            {col.dataType}
                                          </Badge>
                                        </td>
                                        <td className="p-2 text-muted-foreground">
                                          {col.isNullable ? "Yes" : "No"}
                                        </td>
                                        <td className="p-2">
                                          <div className="flex gap-1">
                                            {col.isPrimaryKey && (
                                              <Badge className="bg-primary/10 text-primary border-primary/30 text-xs">
                                                <Key className="h-3 w-3 mr-1" />
                                                PK
                                              </Badge>
                                            )}
                                            {col.isForeignKey && (
                                              <Badge className="bg-accent/10 text-accent-foreground border-accent/30 text-xs">
                                                <Link2 className="h-3 w-3 mr-1" />
                                                FK
                                              </Badge>
                                            )}
                                          </div>
                                        </td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            </CollapsibleContent>
                          </Collapsible>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                )}
              </section>

              {/* Code Patterns Section */}
              <section id="code-patterns" className="space-y-4 animate-fade-in">
                <h2 className="text-2xl font-bold text-foreground">Code Patterns</h2>
                <Card>
                  <CardContent className="pt-6">
                    <ul className="space-y-2">
                      {mockAnalysis.codePatterns.map((pattern, index) => (
                        <li key={index} className="flex items-start gap-2">
                          <ChevronRight className="h-5 w-5 text-primary shrink-0 mt-0.5" />
                          <span className="text-foreground">{pattern}</span>
                        </li>
                      ))}
                    </ul>
                  </CardContent>
                </Card>
              </section>

              {/* Testing Section */}
              <section id="testing" className="space-y-4 animate-fade-in">
                <h2 className="text-2xl font-bold text-foreground">Testing</h2>
                <Card>
                  <CardContent className="pt-6">
                    <div className="flex items-center gap-2">
                      <Badge className="bg-success/10 text-success border-success/30">
                        Testing Framework
                      </Badge>
                      <span className="text-foreground">{mockAnalysis.testingFramework}</span>
                    </div>
                  </CardContent>
                </Card>
              </section>
            </div>
          </main>
        </div>
      )}
    </div>
  );
}

function TocItemComponent({
  item,
  activeSection,
  onSelect,
}: {
  item: TocItem;
  activeSection: string;
  onSelect: (id: string) => void;
}) {
  const [isOpen, setIsOpen] = useState(true);
  const hasChildren = item.children && item.children.length > 0;
  const isActive = activeSection === item.id;

  if (hasChildren) {
    return (
      <Collapsible open={isOpen} onOpenChange={setIsOpen}>
        <CollapsibleTrigger asChild>
          <button
            className={cn(
              "flex items-center justify-between w-full px-3 py-2 text-sm rounded-md hover-elevate",
              isActive && "bg-sidebar-accent text-sidebar-accent-foreground font-medium"
            )}
            onClick={() => onSelect(item.id)}
            data-testid={`toc-item-${item.id}`}
          >
            <span>{item.title}</span>
            <ChevronDown
              className={cn(
                "h-4 w-4 text-muted-foreground transition-transform",
                isOpen && "rotate-180"
              )}
            />
          </button>
        </CollapsibleTrigger>
        <CollapsibleContent className="pl-4 space-y-1 mt-1">
          {item.children?.map((child) => (
            <TocItemComponent
              key={child.id}
              item={child}
              activeSection={activeSection}
              onSelect={onSelect}
            />
          ))}
        </CollapsibleContent>
      </Collapsible>
    );
  }

  return (
    <button
      className={cn(
        "flex items-center w-full px-3 py-2 text-sm rounded-md hover-elevate text-left",
        isActive && "bg-sidebar-accent text-sidebar-accent-foreground font-medium",
        item.level > 0 && "text-muted-foreground"
      )}
      onClick={() => onSelect(item.id)}
      data-testid={`toc-item-${item.id}`}
    >
      {item.title}
    </button>
  );
}
