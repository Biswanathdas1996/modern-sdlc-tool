import { useState, useEffect, useRef } from "react";
import { useLocation } from "wouter";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  FileCheck,
  Download,
  ChevronRight,
  ChevronDown,
  Target,
  CheckCircle2,
  AlertTriangle,
  ArrowRight,
  RefreshCw,
  Edit3,
  FileText,
  Link2,
  Bookmark,
  Users,
  Loader2,
  GitBranch,
  Plus,
  BookOpen,
} from "lucide-react";
import { SiJira, SiConfluence } from "react-icons/si";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { WorkflowHeader } from "@/components/WorkflowHeader";
import { LoadingSpinner, LoadingOverlay } from "@/components/LoadingSpinner";
import { EmptyState } from "@/components/EmptyState";
import { apiRequest } from "@/lib/queryClient";
import { cn } from "@/lib/utils";
import { useToast } from "@/hooks/use-toast";
import { useSession } from "@/hooks/useSession";
import type { BRD, KnowledgeSource } from "@shared/schema";

interface RelatedJiraStory {
  story: {
    key: string;
    summary: string;
    description: string;
    status: string;
    priority: string;
    labels: string[];
  };
  relevanceScore: number;
  reason: string;
}

const workflowSteps = [
  { id: "analyze", label: "Analyze", completed: true, active: false },
  { id: "document", label: "Document", completed: true, active: false },
  { id: "requirements", label: "Requirements", completed: true, active: false },
  { id: "brd", label: "BRD", completed: false, active: true },
  { id: "user-stories", label: "Stories", completed: false, active: false },
  { id: "test-cases", label: "Tests", completed: false, active: false },
  { id: "test-data", label: "Data", completed: false, active: false },
];

export default function BRDPage() {
  const [streamingContent, setStreamingContent] = useState<string>("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingKnowledgeSources, setStreamingKnowledgeSources] = useState<KnowledgeSource[]>([]);
  const [, navigate] = useLocation();
  const queryClient = useQueryClient();
  const contentRef = useRef<HTMLDivElement>(null);
  const { toast } = useToast();
  const { saveSessionArtifact, getSessionArtifact } = useSession();
  
  // Related stories state
  const [relatedStoriesDialogOpen, setRelatedStoriesDialogOpen] = useState(false);
  const [relatedStories, setRelatedStories] = useState<RelatedJiraStory[]>([]);
  const [selectedParentKey, setSelectedParentKey] = useState<string | null>(null);
  const [creationMode, setCreationMode] = useState<"subtask" | "new">("new");
  const [isCheckingRelated, setIsCheckingRelated] = useState(false);

  const { data: brd, isLoading: brdLoading, error } = useQuery<BRD>({
    queryKey: ["/api/brd/current"],
  });

  useEffect(() => {
    if (brd) saveSessionArtifact("brd", brd);
  }, [brd, saveSessionArtifact]);

  const regenerateMutation = useMutation({
    mutationFn: async () => {
      setIsStreaming(true);
      setStreamingContent("");
      setStreamingKnowledgeSources([]);

      const cachedDocumentation = getSessionArtifact("documentation");
      const cachedFeatureRequest = getSessionArtifact("featureRequest");
      const cachedAnalysis = getSessionArtifact("analysis");
      const cachedDatabaseSchema = getSessionArtifact("databaseSchema");
      const response = await fetch("/api/brd/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          documentation: cachedDocumentation,
          featureRequest: cachedFeatureRequest,
          analysis: cachedAnalysis,
          databaseSchema: cachedDatabaseSchema,
        }),
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
              if (data.knowledgeSources) {
                setStreamingKnowledgeSources(data.knowledgeSources);
              }
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

  const generateStoriesMutation = useMutation({
    mutationFn: async (parentKey?: string) => {
      const body: Record<string, any> = {};
      if (parentKey) body.parentJiraKey = parentKey;
      const cachedBrd = getSessionArtifact("brd");
      if (cachedBrd) body.brdData = cachedBrd;
      const cachedDocumentation = getSessionArtifact("documentation");
      if (cachedDocumentation) body.documentation = cachedDocumentation;
      const response = await apiRequest("POST", "/api/user-stories/generate", body);
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/user-stories", brd?.id] });
      setRelatedStoriesDialogOpen(false);
      setSelectedParentKey(null);
      setCreationMode("new");
      toast({
        title: "User Stories Generated",
        description: "User stories have been successfully generated from the BRD.",
      });
      navigate("/user-stories");
    },
    onError: (error: any) => {
      toast({
        title: "Generation Failed",
        description: error?.message || "Failed to generate user stories. Please try regenerating the BRD first.",
        variant: "destructive",
      });
    },
  });

  // Check for related JIRA stories before generating
  const checkRelatedStories = async () => {
    if (!brd) return;
    
    setIsCheckingRelated(true);
    try {
      const featureDescription = `${brd.title}\n\n${brd.content.overview}\n\nObjectives:\n${brd.content.objectives.join("\n")}`;
      
      console.log("Checking for related JIRA stories...");
      const response = await apiRequest("POST", "/api/jira/find-related", {
        featureDescription,
      });
      const data = await response.json();
      console.log("Related stories response:", data);
      
      if (data.relatedStories && data.relatedStories.length > 0) {
        console.log("Found related stories:", data.relatedStories.length);
        const mapped = data.relatedStories.map((s: any) => ({
          story: {
            key: s.key || s.story?.key || "",
            summary: s.summary || s.story?.summary || "",
            description: s.description || s.story?.description || "",
            status: s.status || s.story?.status || "",
            priority: s.priority || s.story?.priority || "",
            labels: s.labels || s.story?.labels || [],
          },
          relevanceScore: s.relevanceScore || 0,
          reason: s.reason || "",
        }));
        setRelatedStories(mapped);
        setRelatedStoriesDialogOpen(true);
      } else {
        console.log("No related stories found, generating directly");
        // No related stories found, generate directly
        generateStoriesMutation.mutate(undefined);
      }
    } catch (error) {
      console.error("Error checking related stories:", error);
      // If error, just proceed with generation
      generateStoriesMutation.mutate(undefined);
    } finally {
      setIsCheckingRelated(false);
    }
  };

  const publishToConfluenceMutation = useMutation({
    mutationFn: async () => {
      const response = await apiRequest("POST", "/api/confluence/publish", {
        brdId: brd?.id,
      });
      return response.json();
    },
    onSuccess: (data) => {
      toast({
        title: "Published to Confluence",
        description: `BRD published successfully. View at: ${data.pageUrl}`,
      });
    },
    onError: (error: any) => {
      toast({
        title: "Confluence Publish Failed",
        description: error.message || "Failed to publish BRD to Confluence",
        variant: "destructive",
      });
    },
  });

  const handleGenerateWithChoice = () => {
    if (creationMode === "subtask" && selectedParentKey) {
      generateStoriesMutation.mutate(selectedParentKey);
    } else {
      generateStoriesMutation.mutate(undefined);
    }
  };

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
    requestType: "feature",
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
                  <Button 
                    variant="outline" 
                    onClick={() => publishToConfluenceMutation.mutate()}
                    disabled={publishToConfluenceMutation.isPending || !brd}
                    data-testid="button-publish-confluence"
                  >
                    {publishToConfluenceMutation.isPending ? (
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    ) : (
                      <SiConfluence className="h-4 w-4 mr-2" />
                    )}
                    Publish to Confluence
                  </Button>
                </div>
              </div>
            </CardHeader>
          </Card>

          {/* Knowledge Base Sources Banner */}
          {(mockBRD.knowledgeSources && mockBRD.knowledgeSources.length > 0) || (isStreaming && streamingKnowledgeSources.length > 0) ? (
            <Card className="border-primary/30 bg-primary/5">
              <CardHeader className="pb-3">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-md bg-primary/10">
                    <BookOpen className="h-5 w-5 text-primary" />
                  </div>
                  <div className="flex-1">
                    <CardTitle className="text-base">Knowledge Base Sources</CardTitle>
                    <CardDescription>
                      {(isStreaming ? streamingKnowledgeSources : mockBRD.knowledgeSources)?.length || 0} chunks extracted and used to generate this BRD
                    </CardDescription>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => navigate("/knowledge-base")}
                    data-testid="button-view-knowledge-base"
                  >
                    <BookOpen className="h-4 w-4 mr-2" />
                    View Knowledge Base
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="pt-0">
                <Accordion type="single" collapsible className="w-full">
                  <AccordionItem value="sources" className="border-none">
                    <AccordionTrigger className="hover:no-underline py-2 text-sm text-muted-foreground">
                      <span className="flex items-center gap-2">
                        <ChevronDown className="h-4 w-4" />
                        View extracted chunks
                      </span>
                    </AccordionTrigger>
                    <AccordionContent>
                      <div className="space-y-3 mt-2">
                        {(isStreaming ? streamingKnowledgeSources : mockBRD.knowledgeSources)?.map((source, index) => (
                          <div key={index} className="p-3 rounded-md bg-background border">
                            <div className="flex items-center gap-2 mb-2">
                              <Badge variant="outline" className="text-xs font-mono">
                                Chunk {index + 1}
                              </Badge>
                              <span className="text-sm font-medium text-foreground">{source.filename}</span>
                            </div>
                            <p className="text-sm text-muted-foreground whitespace-pre-wrap">
                              {source.chunkPreview}
                            </p>
                          </div>
                        ))}
                      </div>
                    </AccordionContent>
                  </AccordionItem>
                </Accordion>
              </CardContent>
            </Card>
          ) : mockBRD.sourceDocumentation ? (
            <Card className="border-primary/30 bg-primary/5">
              <CardContent className="py-4">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-md bg-primary/10">
                    <Link2 className="h-5 w-5 text-primary" />
                  </div>
                  <div className="flex-1">
                    <p className="text-sm font-medium text-foreground">Based on Technical Documentation</p>
                    <p className="text-sm text-muted-foreground">
                      This BRD was generated using "{mockBRD.sourceDocumentation}" as the context source
                    </p>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => navigate("/documentation")}
                    data-testid="button-view-source-docs"
                  >
                    <FileText className="h-4 w-4 mr-2" />
                    View Documentation
                  </Button>
                </div>
              </CardContent>
            </Card>
          ) : null}

          {/* Existing System Context */}
          {mockBRD.content.existingSystemContext && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Link2 className="h-5 w-5 text-primary" />
                  Existing System Context
                </CardTitle>
                <CardDescription>
                  Components, APIs, and data models from the documentation that this feature interacts with
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid md:grid-cols-3 gap-4">
                  {mockBRD.content.existingSystemContext.relevantComponents?.length > 0 && (
                    <div>
                      <h4 className="text-sm font-medium mb-2">Related Components</h4>
                      <ul className="space-y-1">
                        {mockBRD.content.existingSystemContext.relevantComponents.map((comp, i) => (
                          <li key={i} className="text-sm text-muted-foreground flex items-center gap-1">
                            <span className="w-1.5 h-1.5 bg-primary rounded-full" />
                            {comp}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {mockBRD.content.existingSystemContext.relevantAPIs?.length > 0 && (
                    <div>
                      <h4 className="text-sm font-medium mb-2">Related APIs</h4>
                      <ul className="space-y-1">
                        {mockBRD.content.existingSystemContext.relevantAPIs.map((api, i) => (
                          <li key={i} className="text-sm text-muted-foreground flex items-center gap-1">
                            <span className="w-1.5 h-1.5 bg-success rounded-full" />
                            {api}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {mockBRD.content.existingSystemContext.dataModelsAffected?.length > 0 && (
                    <div>
                      <h4 className="text-sm font-medium mb-2">Data Models Affected</h4>
                      <ul className="space-y-1">
                        {mockBRD.content.existingSystemContext.dataModelsAffected.map((model, i) => (
                          <li key={i} className="text-sm text-muted-foreground flex items-center gap-1">
                            <span className="w-1.5 h-1.5 bg-warning rounded-full" />
                            {model}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          )}

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

          {/* Generate User Stories Action */}
          <div className="flex justify-between gap-3 pt-4">
            <Button variant="outline" onClick={() => navigate("/requirements")}>
              Back
            </Button>
            <Button
              onClick={checkRelatedStories}
              disabled={generateStoriesMutation.isPending || isCheckingRelated || !brd}
              data-testid="button-generate-user-stories"
            >
              {generateStoriesMutation.isPending || isCheckingRelated ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  {isCheckingRelated ? "Checking JIRA..." : "Generating User Stories..."}
                </>
              ) : (
                <>
                  <Bookmark className="h-4 w-4 mr-2" />
                  Generate User Stories
                  <ArrowRight className="ml-2 h-4 w-4" />
                </>
              )}
            </Button>
          </div>
        </div>
      </div>

      {/* Related Stories Dialog */}
      <Dialog open={relatedStoriesDialogOpen} onOpenChange={setRelatedStoriesDialogOpen}>
        <DialogContent className="max-w-2xl max-h-[85vh]">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <SiJira className="h-5 w-5 text-[#0052CC]" />
              Related JIRA Stories Found
            </DialogTitle>
            <DialogDescription>
              We found existing stories in your JIRA board that may be related to this feature.
              Choose how you'd like to proceed.
            </DialogDescription>
          </DialogHeader>
          
          <ScrollArea className="max-h-[50vh] pr-4">
            <div className="space-y-4">
              <RadioGroup
                value={creationMode}
                onValueChange={(value) => {
                  setCreationMode(value as "subtask" | "new");
                  if (value === "new") {
                    setSelectedParentKey(null);
                  }
                }}
              >
                <div className="space-y-3">
                  <div className="flex items-start space-x-3 p-3 rounded-lg border bg-card hover-elevate">
                    <RadioGroupItem value="subtask" id="subtask" className="mt-1" />
                    <div className="flex-1">
                      <Label htmlFor="subtask" className="text-base font-medium cursor-pointer">
                        <GitBranch className="h-4 w-4 inline mr-2" />
                        Create as Subtasks
                      </Label>
                      <p className="text-sm text-muted-foreground mt-1">
                        Generate user stories as subtasks of an existing story. The parent story's context will be used to create more relevant content.
                      </p>
                    </div>
                  </div>
                  
                  <div className="flex items-start space-x-3 p-3 rounded-lg border bg-card hover-elevate">
                    <RadioGroupItem value="new" id="new" className="mt-1" />
                    <div className="flex-1">
                      <Label htmlFor="new" className="text-base font-medium cursor-pointer">
                        <Plus className="h-4 w-4 inline mr-2" />
                        Create as New Stories
                      </Label>
                      <p className="text-sm text-muted-foreground mt-1">
                        Generate user stories as independent stories that will be synced to JIRA as new issues.
                      </p>
                    </div>
                  </div>
                </div>
              </RadioGroup>

              {creationMode === "subtask" && (
                <div className="mt-4">
                  <Label className="text-sm font-medium mb-2 block">Select Parent Story:</Label>
                  <div className="space-y-2">
                    {relatedStories.map((related) => (
                      <div
                        key={related.story.key}
                        onClick={() => setSelectedParentKey(related.story.key)}
                        className={cn(
                          "p-3 rounded-lg border cursor-pointer transition-colors",
                          selectedParentKey === related.story.key
                            ? "border-primary bg-primary/5"
                            : "hover-elevate"
                        )}
                        data-testid={`related-story-${related.story.key}`}
                      >
                        <div className="flex items-start justify-between gap-2 flex-wrap">
                          <div className="flex items-center gap-2">
                            <Badge variant="outline" className="font-mono text-xs">
                              {related.story.key}
                            </Badge>
                            <Badge variant="secondary">
                              {related.relevanceScore}% match
                            </Badge>
                            <Badge variant="outline" className="text-xs">
                              {related.story.status}
                            </Badge>
                          </div>
                        </div>
                        <h4 className="font-medium mt-2">{related.story.summary}</h4>
                        <p className="text-sm text-muted-foreground mt-1">{related.reason}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </ScrollArea>

          <DialogFooter className="gap-2 mt-4">
            <Button
              variant="outline"
              onClick={() => setRelatedStoriesDialogOpen(false)}
            >
              Cancel
            </Button>
            <Button
              onClick={handleGenerateWithChoice}
              disabled={
                generateStoriesMutation.isPending ||
                (creationMode === "subtask" && !selectedParentKey)
              }
              data-testid="button-confirm-generation"
            >
              {generateStoriesMutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Generating...
                </>
              ) : (
                <>
                  Generate User Stories
                  <ArrowRight className="h-4 w-4 ml-2" />
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
