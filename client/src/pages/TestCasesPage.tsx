import { useState, useEffect, useMemo } from "react";
import { useSession } from "@/hooks/useSession";
import { useToast } from "@/hooks/use-toast";
import { useLocation, useSearch } from "wouter";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  TestTube,
  Download,
  ArrowRight,
  RefreshCw,
  ChevronDown,
  ChevronRight,
  Play,
  Filter,
  Search,
  Loader2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { WorkflowHeader } from "@/components/WorkflowHeader";
import { LoadingSpinner, LoadingOverlay } from "@/components/LoadingSpinner";
import { CodeBlock } from "@/components/CodeBlock";
import { EmptyState } from "@/components/EmptyState";
import { apiRequest } from "@/lib/queryClient";
import { cn } from "@/lib/utils";
import { useProject } from "@/hooks/useProject";
import type { BRD, TestCase } from "@shared/schema";

const workflowSteps = [
  { id: "analyze", label: "Analyze", completed: true, active: false },
  { id: "document", label: "Document", completed: true, active: false },
  { id: "requirements", label: "Requirements", completed: true, active: false },
  { id: "brd", label: "BRD", completed: true, active: false },
  { id: "user-stories", label: "Stories", completed: true, active: false },
  { id: "test-cases", label: "Tests", completed: false, active: true },
  { id: "test-data", label: "Data", completed: false, active: false },
];

const categoryInfo = {
  happy_path: { label: "Happy Path", description: "Standard successful scenarios", color: "bg-success/10 text-success border-success/30" },
  edge_case: { label: "Edge Cases", description: "Boundary conditions and unusual scenarios", color: "bg-warning/10 text-warning border-warning/30" },
  negative: { label: "Negative Scenarios", description: "Error handling and invalid inputs", color: "bg-destructive/10 text-destructive border-destructive/30" },
  e2e: { label: "End-to-End", description: "Complete user journey tests", color: "bg-primary/10 text-primary border-primary/30" },
};

export default function TestCasesPage() {
  const [expandedTests, setExpandedTests] = useState<Set<string>>(new Set());
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set(["happy_path", "edge_case", "negative", "e2e"]));
  const [filterType, setFilterType] = useState<string>("all");
  const [filterPriority, setFilterPriority] = useState<string>("all");
  const [filterCategory, setFilterCategory] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [, navigate] = useLocation();
  const searchString = useSearch();
  const searchParams = useMemo(() => new URLSearchParams(searchString), [searchString]);
  const brdIdParam = searchParams.get("brd_id");
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const { saveSessionArtifact, getSessionArtifact } = useSession();
  const { currentProjectId } = useProject();

  const { data: brd, isLoading: brdLoading } = useQuery<BRD>({
    queryKey: ["/api/brd/current", currentProjectId, brdIdParam],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (brdIdParam) params.set("brd_id", brdIdParam);
      else if (currentProjectId) params.set("project_id", currentProjectId);
      const res = await fetch(`/api/brd/current?${params.toString()}`, { credentials: "include" });
      if (!res.ok) throw new Error("Failed to fetch");
      return res.json();
    },
  });

  const { data: testCases, isLoading: testCasesLoading } = useQuery<TestCase[]>({
    queryKey: ["/api/test-cases", currentProjectId, brd?.id],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (brd?.id) params.set("brd_id", brd.id);
      else if (currentProjectId) params.set("project_id", currentProjectId);
      const res = await fetch(`/api/test-cases?${params.toString()}`, { credentials: "include" });
      if (!res.ok) throw new Error("Failed to fetch");
      return res.json();
    },
    enabled: !!brd?.id,
  });

  const isLoading = brdLoading || testCasesLoading;

  useEffect(() => {
    if (testCases && testCases.length > 0) saveSessionArtifact("testCases", testCases);
  }, [testCases, saveSessionArtifact]);

  const regenerateMutation = useMutation({
    mutationFn: async () => {
      const body: Record<string, any> = {};
      if (brd?.id) body.brdId = brd.id;
      else if (brdIdParam) body.brdId = brdIdParam;
      const response = await apiRequest("POST", "/api/test-cases/generate", body);
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/test-cases", currentProjectId, brd?.id] });
    },
  });

  const generateTestDataMutation = useMutation({
    mutationFn: async () => {
      const body: Record<string, any> = {};
      if (brd?.id) body.brdId = brd.id;
      else if (brdIdParam) body.brdId = brdIdParam;
      const response = await apiRequest("POST", "/api/test-data/generate", body);
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/test-data", currentProjectId, brd?.id] });
      const brdQuery = brdIdParam ? `?brd_id=${brdIdParam}` : "";
      navigate(`/test-data${brdQuery}`);
    },
    onError: (error: any) => {
      toast({
        title: "Error generating test data",
        description: error?.message || "Please try again",
        variant: "destructive",
      });
    },
  });

  const activeTestCases: TestCase[] = testCases || [];

  const toggleExpand = (id: string) => {
    setExpandedTests((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const filteredTests = activeTestCases.filter((test) => {
    if (filterType !== "all" && test.type !== filterType) return false;
    if (filterPriority !== "all" && test.priority !== filterPriority) return false;
    if (filterCategory !== "all" && (test as any).category !== filterCategory) return false;
    if (searchQuery && !test.title.toLowerCase().includes(searchQuery.toLowerCase())) return false;
    return true;
  });

  // Group tests by category
  const testsByCategory = {
    happy_path: filteredTests.filter((t) => (t as any).category === "happy_path"),
    edge_case: filteredTests.filter((t) => (t as any).category === "edge_case"),
    negative: filteredTests.filter((t) => (t as any).category === "negative"),
    e2e: filteredTests.filter((t) => (t as any).category === "e2e" || !(t as any).category),
  };

  const toggleCategory = (category: string) => {
    setExpandedCategories((prev) => {
      const next = new Set(prev);
      if (next.has(category)) {
        next.delete(category);
      } else {
        next.add(category);
      }
      return next;
    });
  };

  const getTypeColor = (type: string) => {
    switch (type) {
      case "unit":
        return "bg-primary/10 text-primary border-primary/30";
      case "integration":
        return "bg-accent/10 text-accent border-accent/30";
      case "e2e":
        return "bg-success/10 text-success border-success/30";
      case "acceptance":
        return "bg-warning/10 text-warning border-warning/30";
      default:
        return "";
    }
  };

  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case "critical":
        return "bg-destructive/10 text-destructive border-destructive/30";
      case "high":
        return "bg-warning/10 text-warning border-warning/30";
      case "medium":
        return "bg-primary/10 text-primary border-primary/30";
      case "low":
        return "bg-muted text-muted-foreground";
      default:
        return "";
    }
  };

  const handleExport = () => {
    const content = JSON.stringify(activeTestCases, null, 2);
    const blob = new Blob([content], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "test-cases.json";
    a.click();
    URL.revokeObjectURL(url);
  };

  if (!brd && !isLoading) {
    return (
      <div className="container max-w-4xl mx-auto py-8 px-4">
        <EmptyState
          icon="document"
          title="No BRD Available"
          description="Generate a Business Requirements Document first before creating test cases."
          action={{
            label: "Go to BRD",
            onClick: () => window.location.href = brdIdParam ? `/brd?brd_id=${brdIdParam}` : "/brd",
          }}
        />
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex flex-col h-full">
        <WorkflowHeader
          steps={workflowSteps}
          title="Generated Test Cases"
          description="Test cases generated from your BRD requirements."
        />
        <div className="flex-1 flex items-center justify-center">
          <LoadingSpinner size="lg" text="Loading test cases..." />
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {regenerateMutation.isPending && (
        <LoadingOverlay message="Regenerating Test Cases..." subMessage="Analyzing BRD requirements..." />
      )}

      <WorkflowHeader
        steps={workflowSteps}
        title="Generated Test Cases"
        description="Test cases generated from your BRD requirements, ready for implementation."
      />

      <div className="flex-1 overflow-auto p-6">
        <div className="max-w-4xl mx-auto space-y-6">
          {/* Stats & Actions */}
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div className="flex items-center gap-4 flex-wrap">
              <div className="flex items-center gap-2 text-sm flex-wrap">
                <Badge variant="outline">{activeTestCases.length} Total</Badge>
                <Badge variant="outline" className={categoryInfo.happy_path.color}>
                  {testsByCategory.happy_path.length} Happy Path
                </Badge>
                <Badge variant="outline" className={categoryInfo.edge_case.color}>
                  {testsByCategory.edge_case.length} Edge Cases
                </Badge>
                <Badge variant="outline" className={categoryInfo.negative.color}>
                  {testsByCategory.negative.length} Negative
                </Badge>
                <Badge variant="outline" className={categoryInfo.e2e.color}>
                  {testsByCategory.e2e.length} E2E
                </Badge>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                onClick={() => regenerateMutation.mutate()}
                disabled={regenerateMutation.isPending}
                data-testid="button-regenerate-tests"
              >
                <RefreshCw className={cn("h-4 w-4 mr-2", regenerateMutation.isPending && "animate-spin")} />
                Regenerate
              </Button>
              <Button variant="outline" onClick={handleExport} data-testid="button-export-tests">
                <Download className="h-4 w-4 mr-2" />
                Export
              </Button>
            </div>
          </div>

          {/* Filters */}
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center gap-4 flex-wrap">
                <div className="relative flex-1 min-w-[200px]">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    type="search"
                    placeholder="Search test cases..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="pl-9"
                    data-testid="input-search-tests"
                  />
                </div>
                <Select value={filterType} onValueChange={setFilterType}>
                  <SelectTrigger className="w-[150px]" data-testid="select-filter-type">
                    <Filter className="h-4 w-4 mr-2" />
                    <SelectValue placeholder="Type" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Types</SelectItem>
                    <SelectItem value="unit">Unit</SelectItem>
                    <SelectItem value="integration">Integration</SelectItem>
                    <SelectItem value="e2e">E2E</SelectItem>
                    <SelectItem value="acceptance">Acceptance</SelectItem>
                  </SelectContent>
                </Select>
                <Select value={filterCategory} onValueChange={setFilterCategory}>
                  <SelectTrigger className="w-[150px]" data-testid="select-filter-category">
                    <SelectValue placeholder="Category" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Categories</SelectItem>
                    <SelectItem value="happy_path">Happy Path</SelectItem>
                    <SelectItem value="edge_case">Edge Cases</SelectItem>
                    <SelectItem value="negative">Negative</SelectItem>
                    <SelectItem value="e2e">End-to-End</SelectItem>
                  </SelectContent>
                </Select>
                <Select value={filterPriority} onValueChange={setFilterPriority}>
                  <SelectTrigger className="w-[150px]" data-testid="select-filter-priority">
                    <SelectValue placeholder="Priority" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Priorities</SelectItem>
                    <SelectItem value="critical">Critical</SelectItem>
                    <SelectItem value="high">High</SelectItem>
                    <SelectItem value="medium">Medium</SelectItem>
                    <SelectItem value="low">Low</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </CardContent>
          </Card>

          {/* Test Cases List - Grouped by Category */}
          <div className="space-y-6">
            {filteredTests.length === 0 ? (
              <EmptyState
                icon="test"
                title="No test cases generated for this BRD yet."
                description="Try adjusting your filters or generate new test cases."
              />
            ) : (
              (Object.entries(testsByCategory) as [keyof typeof categoryInfo, TestCase[]][]).map(([category, tests]) => {
                if (tests.length === 0) return null;
                const info = categoryInfo[category];
                return (
                  <Collapsible
                    key={category}
                    open={expandedCategories.has(category)}
                    onOpenChange={() => toggleCategory(category)}
                  >
                    <CollapsibleTrigger asChild>
                      <div className="flex items-center justify-between p-4 bg-muted/50 rounded-lg cursor-pointer hover-elevate">
                        <div className="flex items-center gap-3">
                          <Badge className={cn("text-sm", info.color)}>
                            {info.label}
                          </Badge>
                          <span className="text-sm text-muted-foreground">{info.description}</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <Badge variant="outline">{tests.length} tests</Badge>
                          {expandedCategories.has(category) ? (
                            <ChevronDown className="h-5 w-5 text-muted-foreground" />
                          ) : (
                            <ChevronRight className="h-5 w-5 text-muted-foreground" />
                          )}
                        </div>
                      </div>
                    </CollapsibleTrigger>
                    <CollapsibleContent className="mt-3 space-y-3">
                      {tests.map((test) => (
                        <Collapsible
                          key={test.id}
                          open={expandedTests.has(test.id)}
                          onOpenChange={() => toggleExpand(test.id)}
                        >
                          <Card>
                            <CollapsibleTrigger asChild>
                              <CardHeader className="cursor-pointer hover-elevate rounded-t-lg">
                                <div className="flex items-start justify-between gap-4">
                                  <div className="flex items-start gap-3">
                                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-muted mt-1">
                                      <TestTube className="h-4 w-4 text-muted-foreground" />
                                    </div>
                                    <div>
                                      <div className="flex items-center gap-2 flex-wrap">
                                        <Badge variant="outline" className="font-mono text-xs">
                                          {test.id}
                                        </Badge>
                                        <Badge variant="outline" className="font-mono text-xs">
                                          {test.requirementId}
                                        </Badge>
                                      </div>
                                      <CardTitle className="text-base mt-1">{test.title}</CardTitle>
                                      <CardDescription className="mt-1">{test.description}</CardDescription>
                                    </div>
                                  </div>
                                  <div className="flex items-center gap-2 shrink-0">
                                    <Badge variant="outline" className={cn("text-xs", getTypeColor(test.type))}>
                                      {test.type}
                                    </Badge>
                                    <Badge variant="outline" className={cn("text-xs", getPriorityColor(test.priority))}>
                                      {test.priority}
                                    </Badge>
                                    {expandedTests.has(test.id) ? (
                                      <ChevronDown className="h-5 w-5 text-muted-foreground" />
                                    ) : (
                                      <ChevronRight className="h-5 w-5 text-muted-foreground" />
                                    )}
                                  </div>
                                </div>
                              </CardHeader>
                            </CollapsibleTrigger>
                            <CollapsibleContent>
                              <CardContent className="pt-0 space-y-6">
                                {/* Preconditions */}
                                <div>
                                  <h4 className="text-sm font-medium text-foreground mb-2">Preconditions</h4>
                                  <ul className="space-y-1">
                                    {test.preconditions.map((condition, index) => (
                                      <li key={index} className="flex items-center gap-2 text-sm text-muted-foreground">
                                        <div className="h-1.5 w-1.5 rounded-full bg-muted-foreground" />
                                        {condition}
                                      </li>
                                    ))}
                                  </ul>
                                </div>

                                {/* Test Steps */}
                                <div>
                                  <h4 className="text-sm font-medium text-foreground mb-3">Test Steps</h4>
                                  <div className="space-y-3">
                                    {test.steps.map((step) => (
                                      <div key={step.step} className="flex gap-3 p-3 rounded-md bg-muted/50">
                                        <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-xs font-medium">
                                          {step.step}
                                        </div>
                                        <div className="flex-1 space-y-1">
                                          <p className="text-sm font-medium text-foreground">{step.action}</p>
                                          <p className="text-sm text-success">{step.expectedResult}</p>
                                        </div>
                                      </div>
                                    ))}
                                  </div>
                                </div>

                                {/* Expected Outcome */}
                                <div>
                                  <h4 className="text-sm font-medium text-foreground mb-2">Expected Outcome</h4>
                                  <p className="text-sm text-muted-foreground p-3 rounded-md bg-success/5 border border-success/20">
                                    {test.expectedOutcome}
                                  </p>
                                </div>

                                {/* Code Snippet */}
                                {test.codeSnippet && (
                                  <div>
                                    <h4 className="text-sm font-medium text-foreground mb-2">Code Snippet</h4>
                                    <CodeBlock
                                      code={test.codeSnippet}
                                      language="typescript"
                                      filename={`${test.id.toLowerCase()}.test.ts`}
                                    />
                                  </div>
                                )}
                              </CardContent>
                            </CollapsibleContent>
                          </Card>
                        </Collapsible>
                      ))}
                    </CollapsibleContent>
                  </Collapsible>
                );
              })
            )}
          </div>

          {/* Navigation */}
          <div className="flex justify-between gap-3 pt-4">
            <Button variant="outline" onClick={() => navigate("/user-stories")} disabled={generateTestDataMutation.isPending}>
              Back
            </Button>
            <Button 
              onClick={() => generateTestDataMutation.mutate()} 
              disabled={generateTestDataMutation.isPending}
              data-testid="button-next-test-data"
            >
              {generateTestDataMutation.isPending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Generating Test Data...
                </>
              ) : (
                <>
                  Generate Test Data
                  <ArrowRight className="ml-2 h-4 w-4" />
                </>
              )}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
