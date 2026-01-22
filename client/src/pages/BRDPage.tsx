import { useState, useEffect, useRef } from "react";
import { useLocation } from "wouter";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  FileCheck,
  Download,
  ChevronRight,
  Target,
  CheckCircle2,
  AlertTriangle,
  ArrowRight,
  RefreshCw,
  Edit3,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { WorkflowHeader } from "@/components/WorkflowHeader";
import { LoadingSpinner, LoadingOverlay } from "@/components/LoadingSpinner";
import { EmptyState } from "@/components/EmptyState";
import { apiRequest } from "@/lib/queryClient";
import { cn } from "@/lib/utils";
import type { BRD } from "@shared/schema";

const workflowSteps = [
  { id: "analyze", label: "Analyze", completed: true, active: false },
  { id: "document", label: "Document", completed: true, active: false },
  { id: "requirements", label: "Requirements", completed: true, active: false },
  { id: "brd", label: "BRD", completed: false, active: true },
  { id: "test-cases", label: "Tests", completed: false, active: false },
];

export default function BRDPage() {
  const [streamingContent, setStreamingContent] = useState<string>("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [, navigate] = useLocation();
  const queryClient = useQueryClient();
  const contentRef = useRef<HTMLDivElement>(null);

  const { data: brd, isLoading: brdLoading, error } = useQuery<BRD>({
    queryKey: ["/api/brd/current"],
  });

  const regenerateMutation = useMutation({
    mutationFn: async () => {
      setIsStreaming(true);
      setStreamingContent("");

      const response = await fetch("/api/brd/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });

      if (!response.ok) throw new Error("Failed to generate BRD");

      const reader = response.body?.getReader();
      if (!reader) throw new Error("No response body");

      const decoder = new TextDecoder();
      let content = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split("\n");

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.content) {
                content += data.content;
                setStreamingContent(content);
              }
              if (data.done) {
                setIsStreaming(false);
              }
            } catch (e) {
              // Ignore parse errors
            }
          }
        }
      }

      return content;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/brd/current"] });
    },
    onError: () => {
      setIsStreaming(false);
    },
  });

  // Auto-scroll during streaming
  useEffect(() => {
    if (isStreaming && contentRef.current) {
      contentRef.current.scrollTop = contentRef.current.scrollHeight;
    }
  }, [streamingContent, isStreaming]);

  const mockBRD: BRD = brd || {
    id: "1",
    projectId: "1",
    featureRequestId: "1",
    title: "User Dashboard with Analytics",
    version: "1.0",
    status: "draft",
    content: {
      overview:
        "This Business Requirements Document outlines the requirements for implementing a comprehensive user dashboard with analytics capabilities. The dashboard will provide users with real-time insights into their activity, performance metrics, and actionable recommendations.",
      objectives: [
        "Provide users with a centralized view of their key metrics and KPIs",
        "Enable data-driven decision making through visual analytics",
        "Improve user engagement by surfacing relevant insights",
        "Reduce time to insight by consolidating data from multiple sources",
      ],
      scope: {
        inScope: [
          "Dashboard layout and navigation",
          "Real-time data visualization components",
          "User activity tracking and reporting",
          "Customizable widget system",
          "Export functionality for reports",
        ],
        outOfScope: [
          "Advanced machine learning predictions",
          "Third-party integrations (Phase 2)",
          "Mobile native applications",
          "Real-time collaboration features",
        ],
      },
      functionalRequirements: [
        {
          id: "FR-001",
          title: "Dashboard Overview",
          description: "Users shall be able to view a summary dashboard showing key metrics including total users, active sessions, conversion rate, and revenue.",
          priority: "high",
          acceptanceCriteria: [
            "Dashboard loads within 2 seconds",
            "All metrics update in real-time",
            "Data is accurate within 1-minute delay",
            "Dashboard is responsive on all screen sizes",
          ],
        },
        {
          id: "FR-002",
          title: "Analytics Charts",
          description: "Users shall be able to view interactive charts displaying trend data, comparisons, and distributions.",
          priority: "high",
          acceptanceCriteria: [
            "Charts support zoom and pan interactions",
            "Users can select date ranges",
            "Tooltips show detailed values on hover",
            "Charts support data export to CSV",
          ],
        },
        {
          id: "FR-003",
          title: "Custom Widgets",
          description: "Users shall be able to add, remove, and rearrange dashboard widgets according to their preferences.",
          priority: "medium",
          acceptanceCriteria: [
            "Drag-and-drop widget reordering",
            "Widget configurations persist across sessions",
            "At least 10 widget types available",
            "Widgets can be resized within constraints",
          ],
        },
      ],
      nonFunctionalRequirements: [
        {
          id: "NFR-001",
          category: "Performance",
          description: "Dashboard page load time must not exceed 3 seconds on a standard broadband connection.",
        },
        {
          id: "NFR-002",
          category: "Scalability",
          description: "System must support up to 10,000 concurrent dashboard users without performance degradation.",
        },
        {
          id: "NFR-003",
          category: "Accessibility",
          description: "Dashboard must comply with WCAG 2.1 Level AA accessibility standards.",
        },
      ],
      technicalConsiderations: [
        "Integrate with existing React frontend architecture",
        "Use WebSocket connections for real-time updates",
        "Implement caching layer for frequently accessed data",
        "Consider serverless functions for data aggregation",
      ],
      dependencies: [
        "User authentication system (existing)",
        "Analytics data pipeline",
        "Design system components",
      ],
      assumptions: [
        "Users have modern browsers with JavaScript enabled",
        "Backend API endpoints are available and documented",
        "Historical data is available for at least 12 months",
      ],
      risks: [
        {
          description: "Data inconsistency between real-time and historical views",
          mitigation: "Implement data validation layer and clear timestamps",
        },
        {
          description: "Performance issues with large datasets",
          mitigation: "Implement pagination and data aggregation strategies",
        },
      ],
    },
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  };

  const handleExport = () => {
    const content = JSON.stringify(mockBRD, null, 2);
    const blob = new Blob([content], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `BRD-${mockBRD.title.replace(/\s+/g, "-")}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case "high":
        return "bg-destructive/10 text-destructive border-destructive/30";
      case "medium":
        return "bg-warning/10 text-warning border-warning/30";
      case "low":
        return "bg-success/10 text-success border-success/30";
      default:
        return "";
    }
  };

  if (brdLoading && !isStreaming) {
    return (
      <div className="flex flex-col h-full">
        <WorkflowHeader
          steps={workflowSteps}
          title="Business Requirements Document"
          description="Generated BRD based on your feature requirements and repository context."
        />
        <div className="flex-1 flex items-center justify-center">
          <LoadingSpinner size="lg" text="Loading BRD..." />
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {regenerateMutation.isPending && !isStreaming && (
        <LoadingOverlay message="Regenerating BRD..." subMessage="Please wait..." />
      )}

      <WorkflowHeader
        steps={workflowSteps}
        title="Business Requirements Document"
        description="Generated BRD based on your feature requirements and repository context."
      />

      <div className="flex-1 overflow-auto p-6" ref={contentRef}>
        <div className="max-w-4xl mx-auto space-y-6">
          {/* Header Card */}
          <Card>
            <CardHeader>
              <div className="flex items-start justify-between gap-4 flex-wrap">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-md bg-primary/10">
                    <FileCheck className="h-5 w-5 text-primary" />
                  </div>
                  <div>
                    <CardTitle className="text-xl">{mockBRD.title}</CardTitle>
                    <CardDescription className="flex items-center gap-2 mt-1 flex-wrap">
                      <Badge variant="outline">v{mockBRD.version}</Badge>
                      <Badge
                        variant="outline"
                        className={cn(
                          mockBRD.status === "draft" && "bg-muted text-muted-foreground",
                          mockBRD.status === "review" && "bg-warning/10 text-warning",
                          mockBRD.status === "approved" && "bg-success/10 text-success"
                        )}
                      >
                        {mockBRD.status}
                      </Badge>
                    </CardDescription>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    onClick={() => regenerateMutation.mutate()}
                    disabled={regenerateMutation.isPending}
                    data-testid="button-regenerate-brd"
                  >
                    <RefreshCw className={cn("h-4 w-4 mr-2", regenerateMutation.isPending && "animate-spin")} />
                    Regenerate
                  </Button>
                  <Button variant="outline" onClick={handleExport} data-testid="button-export-brd">
                    <Download className="h-4 w-4 mr-2" />
                    Export
                  </Button>
                </div>
              </div>
            </CardHeader>
          </Card>

          {/* Streaming Content */}
          {isStreaming && (
            <Card className="border-primary/50 bg-primary/5">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <div className="h-2 w-2 rounded-full bg-primary animate-pulse" />
                  Generating BRD...
                </CardTitle>
              </CardHeader>
              <CardContent>
                <pre className="whitespace-pre-wrap font-mono text-sm text-foreground">
                  {streamingContent}
                </pre>
              </CardContent>
            </Card>
          )}

          {/* Overview Section */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Target className="h-5 w-5 text-primary" />
                Overview
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-foreground leading-relaxed">{mockBRD.content.overview}</p>
            </CardContent>
          </Card>

          {/* Objectives */}
          <Card>
            <CardHeader>
              <CardTitle>Objectives</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-2">
                {mockBRD.content.objectives.map((objective, index) => (
                  <li key={index} className="flex items-start gap-2">
                    <CheckCircle2 className="h-5 w-5 text-success shrink-0 mt-0.5" />
                    <span className="text-foreground">{objective}</span>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>

          {/* Scope */}
          <div className="grid md:grid-cols-2 gap-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base text-success flex items-center gap-2">
                  <CheckCircle2 className="h-4 w-4" />
                  In Scope
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2">
                  {mockBRD.content.scope.inScope.map((item, index) => (
                    <li key={index} className="flex items-start gap-2">
                      <ChevronRight className="h-4 w-4 text-success shrink-0 mt-0.5" />
                      <span className="text-sm text-foreground">{item}</span>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-base text-muted-foreground flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4" />
                  Out of Scope
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2">
                  {mockBRD.content.scope.outOfScope.map((item, index) => (
                    <li key={index} className="flex items-start gap-2">
                      <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0 mt-0.5" />
                      <span className="text-sm text-muted-foreground">{item}</span>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          </div>

          {/* Functional Requirements */}
          <Card>
            <CardHeader>
              <CardTitle>Functional Requirements</CardTitle>
            </CardHeader>
            <CardContent>
              <Accordion type="multiple" className="w-full">
                {mockBRD.content.functionalRequirements.map((req) => (
                  <AccordionItem key={req.id} value={req.id}>
                    <AccordionTrigger className="hover:no-underline">
                      <div className="flex items-center gap-3">
                        <Badge variant="outline" className="font-mono text-xs">
                          {req.id}
                        </Badge>
                        <span className="font-medium text-left">{req.title}</span>
                        <Badge variant="outline" className={cn("ml-auto", getPriorityColor(req.priority))}>
                          {req.priority}
                        </Badge>
                      </div>
                    </AccordionTrigger>
                    <AccordionContent>
                      <div className="space-y-4 pt-2">
                        <p className="text-muted-foreground">{req.description}</p>
                        <div>
                          <p className="text-sm font-medium text-foreground mb-2">Acceptance Criteria:</p>
                          <ul className="space-y-1">
                            {req.acceptanceCriteria.map((criteria, index) => (
                              <li key={index} className="flex items-start gap-2 text-sm">
                                <CheckCircle2 className="h-4 w-4 text-success shrink-0 mt-0.5" />
                                <span className="text-muted-foreground">{criteria}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      </div>
                    </AccordionContent>
                  </AccordionItem>
                ))}
              </Accordion>
            </CardContent>
          </Card>

          {/* Non-Functional Requirements */}
          <Card>
            <CardHeader>
              <CardTitle>Non-Functional Requirements</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {mockBRD.content.nonFunctionalRequirements.map((req) => (
                  <div key={req.id} className="flex items-start gap-3 p-3 rounded-md bg-muted/50">
                    <Badge variant="outline" className="font-mono text-xs shrink-0">
                      {req.id}
                    </Badge>
                    <div>
                      <p className="text-sm font-medium text-foreground">{req.category}</p>
                      <p className="text-sm text-muted-foreground">{req.description}</p>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Technical Considerations */}
          <Card>
            <CardHeader>
              <CardTitle>Technical Considerations</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-2">
                {mockBRD.content.technicalConsiderations.map((item, index) => (
                  <li key={index} className="flex items-start gap-2">
                    <ChevronRight className="h-4 w-4 text-accent shrink-0 mt-0.5" />
                    <span className="text-foreground">{item}</span>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>

          {/* Risks */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <AlertTriangle className="h-5 w-5 text-warning" />
                Risks & Mitigations
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {mockBRD.content.risks.map((risk, index) => (
                  <div key={index} className="p-4 rounded-md bg-warning/5 border border-warning/20">
                    <p className="font-medium text-foreground mb-2">{risk.description}</p>
                    <p className="text-sm text-muted-foreground">
                      <span className="font-medium text-success">Mitigation:</span> {risk.mitigation}
                    </p>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Navigation */}
          <div className="flex justify-between gap-3 pt-4">
            <Button variant="outline" onClick={() => navigate("/requirements")}>
              Back
            </Button>
            <Button onClick={() => navigate("/test-cases")} data-testid="button-next-test-cases">
              Generate Test Cases
              <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
