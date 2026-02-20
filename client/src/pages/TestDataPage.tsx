import { useState, useEffect } from "react";
import { useSession } from "@/hooks/useSession";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Database,
  Download,
  RefreshCw,
  ChevronDown,
  ChevronRight,
  Copy,
  Check,
  Filter,
  Search,
  FileJson,
  Table,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { WorkflowHeader } from "@/components/WorkflowHeader";
import { LoadingSpinner, LoadingOverlay } from "@/components/LoadingSpinner";
import { EmptyState } from "@/components/EmptyState";
import { apiRequest } from "@/lib/queryClient";
import { cn } from "@/lib/utils";
import { useProject } from "@/hooks/useProject";
import type { TestData } from "@shared/schema";

const workflowSteps = [
  { id: "analyze", label: "Analyze", completed: true, active: false },
  { id: "document", label: "Document", completed: true, active: false },
  { id: "requirements", label: "Requirements", completed: true, active: false },
  { id: "brd", label: "BRD", completed: true, active: false },
  { id: "user-stories", label: "Stories", completed: true, active: false },
  { id: "test-cases", label: "Tests", completed: true, active: false },
  { id: "test-data", label: "Data", completed: false, active: true },
];

export default function TestDataPage() {
  const [expandedData, setExpandedData] = useState<Set<string>>(new Set());
  const [filterType, setFilterType] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const { saveSessionArtifact, getSessionArtifact } = useSession();
  const { currentProjectId } = useProject();

  const { data: testData, isLoading } = useQuery<TestData[]>({
    queryKey: ["/api/test-data", currentProjectId],
    queryFn: async () => {
      const url = currentProjectId ? `/api/test-data?project_id=${currentProjectId}` : `/api/test-data`;
      const res = await fetch(url, { credentials: "include" });
      if (!res.ok) throw new Error("Failed to fetch");
      return res.json();
    },
  });

  useEffect(() => {
    if (testData && testData.length > 0) saveSessionArtifact("testData", testData);
  }, [testData, saveSessionArtifact]);

  const regenerateMutation = useMutation({
    mutationFn: async () => {
      const body: Record<string, any> = {};
      const cachedTestCases = getSessionArtifact("testCases");
      if (cachedTestCases) body.testCases = cachedTestCases;
      const response = await apiRequest("POST", "/api/test-data/generate", body);
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/test-data", currentProjectId] });
    },
  });

  const mockTestData: TestData[] = testData || [
    {
      id: "TD-001",
      testCaseId: "TC-001",
      name: "Valid User Dashboard Data",
      description: "Standard user with active subscription and complete profile",
      dataType: "valid",
      data: {
        user: {
          id: "usr_123456",
          email: "john.doe@example.com",
          name: "John Doe",
          role: "admin",
          subscription: "premium",
          createdAt: "2024-01-15T10:30:00Z",
        },
        metrics: {
          totalUsers: 1250,
          activeSessions: 89,
          conversionRate: 3.5,
          monthlyRevenue: 45000,
        },
        preferences: {
          theme: "dark",
          notifications: true,
          dashboardLayout: "default",
        },
      },
      createdAt: new Date().toISOString(),
    },
    {
      id: "TD-002",
      testCaseId: "TC-001",
      name: "Edge Case - Zero Metrics",
      description: "New user with no activity data",
      dataType: "edge",
      data: {
        user: {
          id: "usr_789012",
          email: "new.user@example.com",
          name: "New User",
          role: "user",
          subscription: "free",
          createdAt: new Date().toISOString(),
        },
        metrics: {
          totalUsers: 0,
          activeSessions: 0,
          conversionRate: 0,
          monthlyRevenue: 0,
        },
        preferences: {
          theme: "light",
          notifications: true,
          dashboardLayout: "default",
        },
      },
      createdAt: new Date().toISOString(),
    },
    {
      id: "TD-003",
      testCaseId: "TC-001",
      name: "Boundary - Maximum Values",
      description: "User with maximum allowed values for all metrics",
      dataType: "boundary",
      data: {
        user: {
          id: "usr_999999",
          email: "max.user@example.com",
          name: "Max User",
          role: "superadmin",
          subscription: "enterprise",
          createdAt: "2020-01-01T00:00:00Z",
        },
        metrics: {
          totalUsers: 10000000,
          activeSessions: 1000000,
          conversionRate: 100,
          monthlyRevenue: 999999999,
        },
        preferences: {
          theme: "system",
          notifications: true,
          dashboardLayout: "custom",
        },
      },
      createdAt: new Date().toISOString(),
    },
    {
      id: "TD-004",
      testCaseId: "TC-002",
      name: "Invalid - Missing Required Fields",
      description: "User data with missing required fields for validation testing",
      dataType: "invalid",
      data: {
        user: {
          id: null,
          email: "",
          name: null,
          role: "unknown",
          subscription: null,
        },
        metrics: null,
        preferences: {},
      },
      createdAt: new Date().toISOString(),
    },
    {
      id: "TD-005",
      testCaseId: "TC-003",
      name: "Chart Data - Time Series",
      description: "Sample time series data for chart testing",
      dataType: "valid",
      data: {
        chartData: [
          { date: "2024-01-01", value: 150, category: "sales" },
          { date: "2024-01-02", value: 200, category: "sales" },
          { date: "2024-01-03", value: 180, category: "sales" },
          { date: "2024-01-04", value: 250, category: "sales" },
          { date: "2024-01-05", value: 220, category: "sales" },
          { date: "2024-01-06", value: 300, category: "sales" },
          { date: "2024-01-07", value: 280, category: "sales" },
        ],
        metadata: {
          startDate: "2024-01-01",
          endDate: "2024-01-07",
          aggregation: "daily",
          currency: "USD",
        },
      },
      createdAt: new Date().toISOString(),
    },
    {
      id: "TD-006",
      testCaseId: "TC-004",
      name: "Widget Configuration",
      description: "Sample widget configuration for drag-drop testing",
      dataType: "valid",
      data: {
        widgets: [
          { id: "w1", type: "metrics", position: { x: 0, y: 0 }, size: { w: 2, h: 1 } },
          { id: "w2", type: "chart", position: { x: 2, y: 0 }, size: { w: 2, h: 2 } },
          { id: "w3", type: "table", position: { x: 0, y: 1 }, size: { w: 2, h: 2 } },
          { id: "w4", type: "activity", position: { x: 0, y: 3 }, size: { w: 4, h: 1 } },
        ],
        gridSettings: {
          columns: 4,
          rowHeight: 150,
          gap: 16,
        },
      },
      createdAt: new Date().toISOString(),
    },
  ];

  const toggleExpand = (id: string) => {
    setExpandedData((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const copyToClipboard = async (id: string, data: Record<string, unknown>) => {
    await navigator.clipboard.writeText(JSON.stringify(data, null, 2));
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const filteredData = mockTestData.filter((data) => {
    if (filterType !== "all" && data.dataType !== filterType) return false;
    if (searchQuery && !data.name.toLowerCase().includes(searchQuery.toLowerCase())) return false;
    return true;
  });

  const getTypeColor = (type: string) => {
    switch (type) {
      case "valid":
        return "bg-success/10 text-success border-success/30";
      case "invalid":
        return "bg-destructive/10 text-destructive border-destructive/30";
      case "edge":
        return "bg-warning/10 text-warning border-warning/30";
      case "boundary":
        return "bg-accent/10 text-accent border-accent/30";
      default:
        return "";
    }
  };

  const handleExport = () => {
    const content = JSON.stringify(mockTestData.map((d) => d.data), null, 2);
    const blob = new Blob([content], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "test-data.json";
    a.click();
    URL.revokeObjectURL(url);
  };

  if (isLoading) {
    return (
      <div className="flex flex-col h-full">
        <WorkflowHeader
          steps={workflowSteps}
          title="Generated Test Data"
          description="Test data generated for your test cases."
        />
        <div className="flex-1 flex items-center justify-center">
          <LoadingSpinner size="lg" text="Loading test data..." />
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {regenerateMutation.isPending && (
        <LoadingOverlay message="Regenerating Test Data..." subMessage="Creating test datasets..." />
      )}

      <WorkflowHeader
        steps={workflowSteps}
        title="Generated Test Data"
        description="Test data generated for your test cases, including valid, invalid, edge, and boundary cases."
      />

      <div className="flex-1 overflow-auto p-6">
        <div className="max-w-4xl mx-auto space-y-6">
          {/* Stats & Actions */}
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div className="flex items-center gap-4 flex-wrap">
              <div className="flex items-center gap-2 text-sm">
                <Badge variant="outline">{mockTestData.length} Datasets</Badge>
                <Badge variant="outline" className={getTypeColor("valid")}>
                  {mockTestData.filter((t) => t.dataType === "valid").length} Valid
                </Badge>
                <Badge variant="outline" className={getTypeColor("invalid")}>
                  {mockTestData.filter((t) => t.dataType === "invalid").length} Invalid
                </Badge>
                <Badge variant="outline" className={getTypeColor("edge")}>
                  {mockTestData.filter((t) => t.dataType === "edge").length} Edge
                </Badge>
                <Badge variant="outline" className={getTypeColor("boundary")}>
                  {mockTestData.filter((t) => t.dataType === "boundary").length} Boundary
                </Badge>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                onClick={() => regenerateMutation.mutate()}
                disabled={regenerateMutation.isPending}
                data-testid="button-regenerate-data"
              >
                <RefreshCw className={cn("h-4 w-4 mr-2", regenerateMutation.isPending && "animate-spin")} />
                Regenerate
              </Button>
              <Button variant="outline" onClick={handleExport} data-testid="button-export-data">
                <Download className="h-4 w-4 mr-2" />
                Export All
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
                    placeholder="Search test data..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="pl-9"
                    data-testid="input-search-data"
                  />
                </div>
                <Select value={filterType} onValueChange={setFilterType}>
                  <SelectTrigger className="w-[150px]" data-testid="select-filter-data-type">
                    <Filter className="h-4 w-4 mr-2" />
                    <SelectValue placeholder="Type" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Types</SelectItem>
                    <SelectItem value="valid">Valid</SelectItem>
                    <SelectItem value="invalid">Invalid</SelectItem>
                    <SelectItem value="edge">Edge Case</SelectItem>
                    <SelectItem value="boundary">Boundary</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </CardContent>
          </Card>

          {/* Test Data List */}
          <div className="space-y-4">
            {filteredData.length === 0 ? (
              <EmptyState
                icon="data"
                title="No test data found"
                description="Try adjusting your filters or generate new test data."
              />
            ) : (
              filteredData.map((data) => (
                <Collapsible
                  key={data.id}
                  open={expandedData.has(data.id)}
                  onOpenChange={() => toggleExpand(data.id)}
                >
                  <Card>
                    <CollapsibleTrigger asChild>
                      <CardHeader className="cursor-pointer hover-elevate rounded-t-lg">
                        <div className="flex items-start justify-between gap-4">
                          <div className="flex items-start gap-3">
                            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-muted mt-1">
                              <Database className="h-4 w-4 text-muted-foreground" />
                            </div>
                            <div>
                              <div className="flex items-center gap-2 flex-wrap">
                                <Badge variant="outline" className="font-mono text-xs">
                                  {data.id}
                                </Badge>
                                <Badge variant="outline" className="font-mono text-xs">
                                  {data.testCaseId}
                                </Badge>
                              </div>
                              <CardTitle className="text-base mt-1">{data.name}</CardTitle>
                              <CardDescription className="mt-1">{data.description}</CardDescription>
                            </div>
                          </div>
                          <div className="flex items-center gap-2 shrink-0">
                            <Badge variant="outline" className={cn("text-xs", getTypeColor(data.dataType))}>
                              {data.dataType}
                            </Badge>
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={(e) => {
                                e.stopPropagation();
                                copyToClipboard(data.id, data.data);
                              }}
                              data-testid={`button-copy-data-${data.id}`}
                            >
                              {copiedId === data.id ? (
                                <Check className="h-4 w-4 text-success" />
                              ) : (
                                <Copy className="h-4 w-4" />
                              )}
                            </Button>
                            {expandedData.has(data.id) ? (
                              <ChevronDown className="h-5 w-5 text-muted-foreground" />
                            ) : (
                              <ChevronRight className="h-5 w-5 text-muted-foreground" />
                            )}
                          </div>
                        </div>
                      </CardHeader>
                    </CollapsibleTrigger>
                    <CollapsibleContent>
                      <CardContent className="pt-0">
                        <Tabs defaultValue="json" className="w-full">
                          <TabsList className="mb-4">
                            <TabsTrigger value="json" className="flex items-center gap-2">
                              <FileJson className="h-4 w-4" />
                              JSON
                            </TabsTrigger>
                            <TabsTrigger value="table" className="flex items-center gap-2">
                              <Table className="h-4 w-4" />
                              Table
                            </TabsTrigger>
                          </TabsList>
                          <TabsContent value="json">
                            <div className="relative">
                              <ScrollArea className="h-[300px] rounded-md border border-border bg-muted/50">
                                <pre className="p-4 font-mono text-sm">
                                  <code>{JSON.stringify(data.data, null, 2)}</code>
                                </pre>
                              </ScrollArea>
                            </div>
                          </TabsContent>
                          <TabsContent value="table">
                            <ScrollArea className="h-[300px]">
                              <div className="rounded-md border border-border overflow-hidden">
                                <table className="w-full text-sm">
                                  <thead className="bg-muted">
                                    <tr>
                                      <th className="px-4 py-2 text-left font-medium">Key</th>
                                      <th className="px-4 py-2 text-left font-medium">Value</th>
                                      <th className="px-4 py-2 text-left font-medium">Type</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {renderTableRows(data.data)}
                                  </tbody>
                                </table>
                              </div>
                            </ScrollArea>
                          </TabsContent>
                        </Tabs>
                      </CardContent>
                    </CollapsibleContent>
                  </Card>
                </Collapsible>
              ))
            )}
          </div>

          {/* Completion Message */}
          <Card className="border-success bg-success/5">
            <CardContent className="pt-6">
              <div className="flex items-center gap-4">
                <div className="flex h-12 w-12 items-center justify-center rounded-full bg-success/10">
                  <Check className="h-6 w-6 text-success" />
                </div>
                <div>
                  <h3 className="font-semibold text-foreground">Workflow Complete!</h3>
                  <p className="text-sm text-muted-foreground">
                    You have successfully generated documentation, BRD, test cases, and test data for your feature request.
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function renderTableRows(obj: Record<string, unknown>, prefix = ""): React.ReactNode[] {
  const rows: React.ReactNode[] = [];

  for (const [key, value] of Object.entries(obj)) {
    const fullKey = prefix ? `${prefix}.${key}` : key;

    if (value && typeof value === "object" && !Array.isArray(value)) {
      rows.push(...renderTableRows(value as Record<string, unknown>, fullKey));
    } else {
      rows.push(
        <tr key={fullKey} className="border-t border-border">
          <td className="px-4 py-2 font-mono text-xs text-muted-foreground">{fullKey}</td>
          <td className="px-4 py-2">
            {Array.isArray(value) ? (
              <Badge variant="outline" className="font-mono text-xs">
                Array[{value.length}]
              </Badge>
            ) : value === null ? (
              <span className="text-muted-foreground italic">null</span>
            ) : (
              <span className="font-mono text-xs">{String(value)}</span>
            )}
          </td>
          <td className="px-4 py-2">
            <Badge variant="secondary" className="text-xs">
              {value === null ? "null" : Array.isArray(value) ? "array" : typeof value}
            </Badge>
          </td>
        </tr>
      );
    }
  }

  return rows;
}
