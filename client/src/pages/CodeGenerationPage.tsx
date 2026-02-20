import { useState, useEffect, useRef, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocation } from "wouter";
import { ArrowLeft, ArrowRight, Code2, Wand2, GitBranch, Loader2, CheckCircle2, Circle, AlertCircle, ExternalLink, FileCode, FilePlus, FilePen, ChevronDown, ChevronRight, Copy, Check, Clock, FolderGit2, Layers, XCircle, RefreshCw, Maximize2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import { WorkflowHeader } from "@/components/WorkflowHeader";
import { EmptyState } from "@/components/EmptyState";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { apiRequest } from "@/lib/queryClient";
import { useToast } from "@/hooks/use-toast";
import { useSession } from "@/hooks/useSession";
import { useProject } from "@/hooks/useProject";
import type { BRD, UserStory } from "@shared/schema";

const workflowSteps = [
  { id: "analyze", label: "Analyze", completed: true, active: false },
  { id: "document", label: "Document", completed: true, active: false },
  { id: "requirements", label: "Requirements", completed: true, active: false },
  { id: "brd", label: "BRD", completed: true, active: false },
  { id: "user-stories", label: "Stories", completed: true, active: false },
  { id: "code-gen", label: "Code Gen", completed: false, active: true },
  { id: "test-cases", label: "Tests", completed: false, active: false },
  { id: "test-data", label: "Data", completed: false, active: false },
];

interface ProgressStep {
  label: string;
  detail: string;
  status: "pending" | "active" | "done" | "error";
}

interface GeneratedChange {
  file_path: string;
  action: string;
  description: string;
  story_refs: string[];
  success: boolean;
  lines?: number;
  error?: string;
}

interface ThinkingStep {
  type: string;
  content: string;
  tool_name?: string;
}


function parseProgressSteps(progress: string, thinkingSteps: ThinkingStep[]): ProgressStep[] {
  const steps: ProgressStep[] = [
    { label: "Cloning Repository", detail: "", status: "pending" },
    { label: "Analyzing Architecture", detail: "", status: "pending" },
    { label: "Creating Implementation Plan", detail: "", status: "pending" },
    { label: "Generating Code", detail: "", status: "pending" },
  ];

  const stepContents = thinkingSteps.map(s => s.content.toLowerCase());
  const progressLower = progress.toLowerCase();

  const hasContent = (keywords: string[]) => stepContents.some(c => keywords.some(k => c.includes(k)));

  if (hasContent(["linked to repo", "cloned", "repository analyzed"])) {
    steps[0].status = "done";
  }

  if (hasContent(["repository analyzed", "source files"])) {
    steps[0].status = "done";
    steps[1].status = "done";
    const srcStep = thinkingSteps.find(s => /\d+ source files/i.test(s.content));
    if (srcStep) steps[1].detail = srcStep.content;
  }

  if (hasContent(["implementation plan", "file changes"])) {
    steps[0].status = "done";
    steps[1].status = "done";
    steps[2].status = "done";
    const planStep = thinkingSteps.find(s => /implementation plan/i.test(s.content));
    if (planStep) steps[2].detail = planStep.content;
  }

  if (hasContent(["generating code"]) || progressLower.includes("generating code")) {
    steps.slice(0, 3).forEach(s => { if (s.status === "pending") s.status = "done"; });
    steps[3].status = "active";
    steps[3].detail = progress;
  }

  if (progressLower === "complete" || progressLower === "error") {
    steps.forEach(s => { if (s.status !== "error") s.status = "done"; });
  }

  if (!steps.some(s => s.status === "active" || s.status === "done")) {
    steps[0].status = "active";
  }

  return steps;
}

export default function CodeGenerationPage() {
  const [, navigate] = useLocation();
  const { toast } = useToast();
  const { getSessionArtifact, saveSessionArtifact } = useSession();
  const { currentProjectId } = useProject();

  const [isGenerating, setIsGenerating] = useState(false);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string>(() => {
    const current = typeof window !== 'undefined' ? localStorage.getItem("docugen_session_current") : null;
    if (current) {
      try {
        const parsed = JSON.parse(current);
        if (parsed.sessionId) return parsed.sessionId;
      } catch {}
    }
    return crypto.randomUUID();
  });
  const [progressSteps, setProgressSteps] = useState<ProgressStep[]>([]);
  const [thinkingSteps, setThinkingSteps] = useState<ThinkingStep[]>([]);
  const [result, setResult] = useState<string | null>(null);
  const [resultSuccess, setResultSuccess] = useState(false);
  const [generatedChanges, setGeneratedChanges] = useState<GeneratedChange[]>([]);
  const [resultMeta, setResultMeta] = useState<{ repo_name: string; language: string; elapsed: number } | null>(null);
  const [showThinking, setShowThinking] = useState(false);
  const [copilotPrompt, setCopilotPrompt] = useState<string | null>(null);
  const [isLoadingPrompt, setIsLoadingPrompt] = useState(false);
  const [copied, setCopied] = useState(false);

  const [showPushDialog, setShowPushDialog] = useState(false);
  const [pushToken, setPushToken] = useState("");
  const [pushBranch, setPushBranch] = useState("ai-generated-code");
  const [pushCommitMsg, setPushCommitMsg] = useState("feat: AI-generated code implementation");
  const [isPushing, setIsPushing] = useState(false);
  const [pushResult, setPushResult] = useState<{ success: boolean; message: string; pr_url?: string } | null>(null);

  const lastStepCountRef = useRef(0);

  const { data: brd, isLoading: brdLoading } = useQuery<BRD>({
    queryKey: ["/api/brd/current", currentProjectId],
    queryFn: async () => {
      const url = currentProjectId ? `/api/brd/current?project_id=${currentProjectId}` : `/api/brd/current`;
      const res = await fetch(url, { credentials: "include" });
      if (!res.ok) throw new Error("Failed to fetch");
      return res.json();
    },
  });

  const { data: userStories, isLoading: storiesLoading } = useQuery<UserStory[]>({
    queryKey: ["/api/user-stories", brd?.id],
    queryFn: async () => {
      const response = await fetch(`/api/user-stories/${brd?.id}`);
      if (!response.ok) throw new Error("Failed to fetch user stories");
      return response.json();
    },
    enabled: !!brd?.id,
  });

  const { data: projects } = useQuery<any[]>({
    queryKey: ["/api/projects"],
  });

  const currentProject = projects && projects.length > 0 ? projects[0] : null;

  const [promptDialogOpen, setPromptDialogOpen] = useState(false);

  const buildPromptRequestBody = useCallback(() => {
    const body: Record<string, any> = {};
    const cachedBrd = getSessionArtifact("brd");
    if (cachedBrd) body.brd = cachedBrd;
    const cachedStories = getSessionArtifact("userStories");
    if (cachedStories) body.userStories = cachedStories;
    const cachedDocumentation = getSessionArtifact("documentation");
    if (cachedDocumentation) body.documentation = cachedDocumentation;
    const cachedAnalysis = getSessionArtifact("analysis");
    if (cachedAnalysis) body.analysis = cachedAnalysis;
    const cachedSchema = getSessionArtifact("databaseSchema");
    if (cachedSchema) body.databaseSchema = cachedSchema;
    const cachedFeatureRequest = getSessionArtifact("featureRequest");
    if (cachedFeatureRequest) body.featureRequest = cachedFeatureRequest;
    return body;
  }, [getSessionArtifact]);

  const fetchCopilotPrompt = useCallback(async () => {
    if (copilotPrompt || isLoadingPrompt) return;
    setIsLoadingPrompt(true);
    try {
      const sessionPrompt = getSessionArtifact("copilotPrompt") as string | null;
      if (sessionPrompt) {
        setCopilotPrompt(sessionPrompt);
        setIsLoadingPrompt(false);
        return;
      }
      const response = await apiRequest("POST", "/api/copilot-prompt/generate", buildPromptRequestBody());
      const data = await response.json();
      setCopilotPrompt(data.prompt);
      saveSessionArtifact("copilotPrompt", data.prompt);
    } catch (err) {
      console.error("Failed to fetch copilot prompt:", err);
    } finally {
      setIsLoadingPrompt(false);
    }
  }, [copilotPrompt, isLoadingPrompt, getSessionArtifact, saveSessionArtifact, buildPromptRequestBody]);

  const regenerateCopilotPrompt = useCallback(async () => {
    setIsLoadingPrompt(true);
    try {
      const response = await apiRequest("POST", "/api/copilot-prompt/generate", buildPromptRequestBody());
      const data = await response.json();
      setCopilotPrompt(data.prompt);
      saveSessionArtifact("copilotPrompt", data.prompt);
    } catch (err) {
      console.error("Failed to regenerate copilot prompt:", err);
    } finally {
      setIsLoadingPrompt(false);
    }
  }, [saveSessionArtifact, buildPromptRequestBody]);

  useEffect(() => {
    if (userStories && userStories.length > 0 && !copilotPrompt) {
      fetchCopilotPrompt();
    }
  }, [userStories, copilotPrompt, fetchCopilotPrompt]);

  useEffect(() => {
    if (!taskId) return;
    const interval = setInterval(async () => {
      try {
        const response = await fetch(`/api/v1/code-gen/task/${taskId}`);
        const data = await response.json();

        if (data.thinking_steps && data.thinking_steps.length > lastStepCountRef.current) {
          setThinkingSteps(data.thinking_steps);
          lastStepCountRef.current = data.thinking_steps.length;
        }

        const steps = parseProgressSteps(data.progress || "", data.thinking_steps || []);
        setProgressSteps(steps);

        if (data.status === "completed") {
          clearInterval(interval);
          setIsGenerating(false);
          setTaskId(null);
          setResult(data.response || "Code generation completed.");
          setResultSuccess(data.success || false);
          if (data.generated_changes) setGeneratedChanges(data.generated_changes);
          if (data.meta) setResultMeta(data.meta);
          lastStepCountRef.current = 0;
        }
      } catch {
        // polling error, will retry
      }
    }, 2500);
    return () => clearInterval(interval);
  }, [taskId]);

  const handleGenerate = async () => {
    if (!userStories || userStories.length === 0 || !copilotPrompt) return;

    setIsGenerating(true);
    setResult(null);
    setPushResult(null);
    setThinkingSteps([]);
    setProgressSteps([]);
    setGeneratedChanges([]);
    setResultMeta(null);
    lastStepCountRef.current = 0;

    try {
      const sessionDocs = getSessionArtifact("documentation");
      const sessionAnalysis = getSessionArtifact("analysis");
      const sessionSchema = getSessionArtifact("databaseSchema");

      const response = await apiRequest("POST", "/api/v1/code-gen/generate", {
        session_id: sessionId,
        repo_url: currentProject?.repoUrl || "",
        user_stories: userStories.map(s => ({
          storyKey: s.storyKey,
          title: s.title,
          description: s.description,
          acceptanceCriteria: s.acceptanceCriteria,
          priority: s.priority,
          storyPoints: s.storyPoints,
        })),
        copilot_prompt: copilotPrompt,
        documentation: sessionDocs || null,
        analysis: sessionAnalysis || null,
        database_schema: sessionSchema || null,
      });

      const data = await response.json();
      if (data.success && data.task_id) {
        setTaskId(data.task_id);
        setSessionId(data.session_id || sessionId);
        toast({ title: "Code generation started", description: "Analyzing repository and generating code..." });
      } else {
        setIsGenerating(false);
        toast({ title: "Error", description: data.error || "Failed to start code generation", variant: "destructive" });
      }
    } catch (err: any) {
      setIsGenerating(false);
      toast({ title: "Error", description: err.message || "Failed to start code generation", variant: "destructive" });
    }
  };

  const handlePushToGitHub = async () => {
    setIsPushing(true);
    setShowPushDialog(false);
    try {
      const response = await apiRequest("POST", "/api/v1/code-gen/push-to-github", {
        session_id: sessionId,
        github_token: pushToken,
        branch_name: pushBranch,
        commit_message: pushCommitMsg,
      });
      const data = await response.json();
      setPushResult({
        success: data.success,
        message: data.message || data.error || "Unknown result",
        pr_url: data.pr_url,
      });
      if (data.success) {
        toast({ title: "Pushed to GitHub", description: data.message });
      } else {
        toast({ title: "Push failed", description: data.error, variant: "destructive" });
      }
    } catch (err: any) {
      setPushResult({ success: false, message: err.message || "Network error" });
      toast({ title: "Push failed", description: err.message, variant: "destructive" });
    } finally {
      setIsPushing(false);
    }
  };

  const handleCopyPrompt = () => {
    if (copilotPrompt) {
      navigator.clipboard.writeText(copilotPrompt);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  if (brdLoading || storiesLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <LoadingSpinner />
      </div>
    );
  }

  if (!userStories || userStories.length === 0) {
    return (
      <div className="p-6">
        <WorkflowHeader steps={workflowSteps} title="Generate Code" description="AI-powered code generation from user stories" />
        <EmptyState
          title="No User Stories Found"
          description="Generate user stories first to enable code generation."
          action={{ label: "Go to User Stories", onClick: () => navigate("/user-stories") }}
        />
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col overflow-hidden">
      <div className="flex-none p-6 pb-3">
        <WorkflowHeader steps={workflowSteps} title="Generate Code" description="AI-powered code generation from user stories" />
        <div className="flex items-center justify-between mt-4 flex-wrap gap-2">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-md bg-primary">
              <Code2 className="h-5 w-5 text-primary-foreground" />
            </div>
            <div>
              <h1 className="text-2xl font-bold" data-testid="text-page-title">Generate Code</h1>
              <p className="text-sm text-muted-foreground">
                AI-powered code generation from user stories
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <Button variant="outline" onClick={() => navigate("/user-stories")} data-testid="button-back-stories">
              <ArrowLeft className="h-4 w-4 mr-2" />
              User Stories
            </Button>
            <Button variant="outline" onClick={() => navigate("/test-cases")} data-testid="button-next-tests">
              Test Cases
              <ArrowRight className="h-4 w-4 ml-2" />
            </Button>
          </div>
        </div>
      </div>

      <ScrollArea className="flex-1 px-6 pb-6">
        <div className="space-y-4 max-w-5xl">
          <Card data-testid="card-stories-summary">
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                <FileCode className="h-4 w-4" />
                User Stories ({userStories.length})
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {userStories.slice(0, 5).map((story, idx) => (
                  <div key={story.id || idx} className="flex items-start gap-2 text-sm">
                    <Badge variant="outline" className="shrink-0 text-xs">{story.storyKey || `US-${idx + 1}`}</Badge>
                    <span className="text-muted-foreground">{story.title}</span>
                  </div>
                ))}
                {userStories.length > 5 && (
                  <p className="text-xs text-muted-foreground">...and {userStories.length - 5} more</p>
                )}
              </div>
            </CardContent>
          </Card>

          <Card data-testid="card-copilot-prompt">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <CardTitle className="text-base flex items-center gap-2">
                  <Wand2 className="h-4 w-4" />
                  Copilot Prompt
                </CardTitle>
                <div className="flex items-center gap-2">
                  {isLoadingPrompt && (
                    <Badge variant="secondary" className="text-xs">
                      <Loader2 className="h-3 w-3 animate-spin mr-1" />
                      <span>Generating...</span>
                    </Badge>
                  )}
                  {copilotPrompt && (
                    <>
                      <Button variant="outline" size="sm" onClick={regenerateCopilotPrompt} disabled={isLoadingPrompt} data-testid="button-regenerate-prompt">
                        <RefreshCw className="h-3 w-3 mr-1" />
                        Regenerate
                      </Button>
                      <Button variant="outline" size="sm" onClick={() => setPromptDialogOpen(true)} data-testid="button-view-prompt">
                        <Maximize2 className="h-3 w-3 mr-1" />
                        View Full
                      </Button>
                      <Button variant="outline" size="sm" onClick={handleCopyPrompt} data-testid="button-copy-prompt">
                        {copied ? <Check className="h-3 w-3 mr-1" /> : <Copy className="h-3 w-3 mr-1" />}
                        {copied ? "Copied" : "Copy"}
                      </Button>
                    </>
                  )}
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {copilotPrompt ? (
                <div className="bg-muted rounded-md p-4 max-h-48 overflow-y-auto">
                  <div className="text-sm text-foreground" data-testid="text-copilot-prompt">
                    <ReactMarkdown
                      components={{
                        h1: ({ children }) => <h1 className="text-base font-bold mb-2">{children}</h1>,
                        h2: ({ children }) => <h2 className="text-sm font-semibold mt-3 mb-1">{children}</h2>,
                        h3: ({ children }) => <h3 className="text-sm font-semibold mt-2 mb-1">{children}</h3>,
                        p: ({ children }) => <p className="text-sm leading-relaxed mb-2">{children}</p>,
                        ul: ({ children }) => <ul className="space-y-1 mb-2 pl-1">{children}</ul>,
                        ol: ({ children }) => <ol className="space-y-1 mb-2 pl-1 list-decimal list-inside">{children}</ol>,
                        li: ({ children }) => <li className="text-sm flex gap-1.5"><span className="text-muted-foreground shrink-0">-</span><span>{children}</span></li>,
                        strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
                        code: ({ className, children }) => {
                          if (className?.includes('language-')) {
                            return <div className="rounded bg-background border p-2 my-2 overflow-x-auto"><pre className="text-xs font-mono whitespace-pre-wrap">{children}</pre></div>;
                          }
                          return <code className="px-1 py-0.5 rounded bg-background text-xs font-mono">{children}</code>;
                        },
                        pre: ({ children }) => <>{children}</>,
                      }}
                    >
                      {copilotPrompt.length > 800 ? copilotPrompt.slice(0, 800) + "\n\n*Click \"View Full\" to see the complete prompt...*" : copilotPrompt}
                    </ReactMarkdown>
                  </div>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">
                  {isLoadingPrompt ? "Generating copilot prompt..." : "Copilot prompt will be generated automatically."}
                </p>
              )}
            </CardContent>
          </Card>

          <Dialog open={promptDialogOpen} onOpenChange={setPromptDialogOpen}>
            <DialogContent className="max-w-4xl max-h-[80vh]">
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2">
                  <Wand2 className="h-5 w-5 text-primary" />
                  VS Code Copilot Prompt
                </DialogTitle>
                <DialogDescription>
                  Copy this prompt and paste it into VS Code Copilot to implement the features
                </DialogDescription>
              </DialogHeader>
              <div className="flex items-center justify-between gap-2 py-2 border-b">
                <span className="text-sm text-muted-foreground">Generated prompt ready</span>
                <div className="flex items-center gap-2">
                  <Button variant="outline" size="sm" onClick={regenerateCopilotPrompt} disabled={isLoadingPrompt} data-testid="button-dialog-regenerate">
                    {isLoadingPrompt ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Regenerating...</> : <><RefreshCw className="h-4 w-4 mr-2" />Regenerate</>}
                  </Button>
                  <Button variant="outline" size="sm" onClick={handleCopyPrompt} data-testid="button-dialog-copy">
                    {copied ? <><Check className="h-4 w-4 mr-2 text-success" />Copied!</> : <><Copy className="h-4 w-4 mr-2" />Copy to Clipboard</>}
                  </Button>
                </div>
              </div>
              <ScrollArea className="h-[60vh] rounded-md border">
                <div className="p-5">
                  {copilotPrompt ? (
                    <ReactMarkdown
                      components={{
                        h1: ({ children }) => <h1 className="text-xl font-bold text-foreground border-b pb-2 mb-4">{children}</h1>,
                        h2: ({ children }) => <h2 className="text-lg font-semibold text-foreground mt-6 mb-3">{children}</h2>,
                        h3: ({ children }) => <h3 className="text-base font-semibold text-foreground mt-4 mb-2">{children}</h3>,
                        p: ({ children }) => <p className="text-sm text-foreground leading-relaxed mb-3">{children}</p>,
                        ul: ({ children }) => <ul className="space-y-1.5 mb-3 pl-1">{children}</ul>,
                        ol: ({ children }) => <ol className="space-y-1.5 mb-3 pl-1 list-decimal list-inside">{children}</ol>,
                        li: ({ children }) => <li className="text-sm text-foreground flex gap-2"><span className="text-muted-foreground mt-0.5 shrink-0">-</span><span>{children}</span></li>,
                        strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
                        em: ({ children }) => <em className="italic text-muted-foreground">{children}</em>,
                        code: ({ className, children }) => {
                          if (className?.includes('language-')) {
                            return <div className="rounded-md bg-muted border overflow-x-auto my-3"><pre className="p-4 text-xs font-mono text-foreground whitespace-pre-wrap">{children}</pre></div>;
                          }
                          return <code className="px-1.5 py-0.5 rounded bg-muted text-xs font-mono text-foreground">{children}</code>;
                        },
                        pre: ({ children }) => <>{children}</>,
                        hr: () => <hr className="my-4 border-border" />,
                        blockquote: ({ children }) => <blockquote className="border-l-2 border-primary pl-4 my-3 text-sm text-muted-foreground italic">{children}</blockquote>,
                      }}
                    >
                      {copilotPrompt}
                    </ReactMarkdown>
                  ) : (
                    <p className="text-sm text-muted-foreground">Loading...</p>
                  )}
                </div>
              </ScrollArea>
            </DialogContent>
          </Dialog>

          {!result && !isGenerating && (
            <Card data-testid="card-generate-action">
              <CardContent className="py-8">
                <div className="text-center space-y-4">
                  <div className="flex h-16 w-16 items-center justify-center rounded-full bg-primary/10 mx-auto">
                    <Code2 className="h-8 w-8 text-primary" />
                  </div>
                  <div>
                    <h3 className="text-lg font-semibold">Ready to Generate Code</h3>
                    <p className="text-sm text-muted-foreground mt-1">
                      The AI will clone your repository, analyze its architecture, and generate code 
                      that follows your existing patterns and coding standards.
                    </p>
                  </div>
                  <Button
                    size="lg"
                    onClick={handleGenerate}
                    disabled={!copilotPrompt || isLoadingPrompt}
                    data-testid="button-generate-code"
                  >
                    <Wand2 className="h-4 w-4 mr-2" />
                    Generate Code
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {isGenerating && (
            <Card data-testid="card-progress">
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Generating Code...
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {progressSteps.map((step, idx) => (
                    <div key={idx} className="flex items-start gap-3">
                      <div className="mt-0.5 shrink-0">
                        {step.status === "done" && <CheckCircle2 className="h-4 w-4 text-success" />}
                        {step.status === "active" && <Loader2 className="h-4 w-4 animate-spin text-primary" />}
                        {step.status === "pending" && <Circle className="h-4 w-4 text-muted-foreground" />}
                        {step.status === "error" && <AlertCircle className="h-4 w-4 text-destructive" />}
                      </div>
                      <div className="min-w-0">
                        <p className={`text-sm font-medium ${step.status === "pending" ? "text-muted-foreground" : ""}`}>
                          {step.label}
                        </p>
                        {step.detail && (
                          <p className="text-xs text-muted-foreground mt-0.5 truncate">{step.detail}</p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>

                {thinkingSteps.length > 0 && (
                  <div className="mt-4 border-t border-border pt-3">
                    <button
                      className="flex items-center gap-1 text-xs text-muted-foreground hover-elevate rounded px-1 py-0.5"
                      onClick={() => setShowThinking(!showThinking)}
                      data-testid="button-toggle-thinking"
                    >
                      {showThinking ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                      AI Thinking ({thinkingSteps.length} steps)
                    </button>
                    {showThinking && (
                      <div className="mt-2 space-y-1 max-h-48 overflow-y-auto">
                        {thinkingSteps.map((step, idx) => (
                          <div key={idx} className="flex items-start gap-2 text-xs">
                            <span className={`shrink-0 mt-0.5 ${step.type === "tool_result" ? "text-success" : "text-primary"}`}>
                              {step.type === "tool_result" ? <CheckCircle2 className="h-3 w-3" /> : <Circle className="h-3 w-3" />}
                            </span>
                            <span className="text-muted-foreground">{step.content}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {result && (
            <div className="space-y-4" data-testid="card-result">
              <Card>
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between flex-wrap gap-2">
                    <CardTitle className="text-base flex items-center gap-2">
                      {resultSuccess ? (
                        <CheckCircle2 className="h-5 w-5 text-success" />
                      ) : (
                        <AlertCircle className="h-5 w-5 text-destructive" />
                      )}
                      {resultSuccess ? "Code Generation Complete" : "Code Generation Failed"}
                    </CardTitle>
                    {resultSuccess && (
                      <div className="flex items-center gap-2">
                        <Button onClick={() => setShowPushDialog(true)} data-testid="button-push-github">
                          <GitBranch className="h-4 w-4 mr-2" />
                          Push to GitHub
                        </Button>
                        <Button variant="outline" onClick={handleGenerate} data-testid="button-regenerate">
                          <Wand2 className="h-4 w-4 mr-2" />
                          Regenerate
                        </Button>
                      </div>
                    )}
                  </div>
                </CardHeader>
                <CardContent>
                  {resultMeta && (
                    <div className="grid grid-cols-3 gap-3" data-testid="result-stats">
                      <div className="flex items-center gap-2.5 rounded-md border border-border bg-muted/30 px-3 py-2.5">
                        <FolderGit2 className="h-4 w-4 text-muted-foreground shrink-0" />
                        <div className="min-w-0">
                          <p className="text-xs text-muted-foreground">Repository</p>
                          <p className="text-sm font-medium truncate">{resultMeta.repo_name || "Unknown"}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2.5 rounded-md border border-border bg-muted/30 px-3 py-2.5">
                        <Layers className="h-4 w-4 text-muted-foreground shrink-0" />
                        <div className="min-w-0">
                          <p className="text-xs text-muted-foreground">Language</p>
                          <p className="text-sm font-medium capitalize">{resultMeta.language || "Unknown"}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2.5 rounded-md border border-border bg-muted/30 px-3 py-2.5">
                        <Clock className="h-4 w-4 text-muted-foreground shrink-0" />
                        <div className="min-w-0">
                          <p className="text-xs text-muted-foreground">Duration</p>
                          <p className="text-sm font-medium">{resultMeta.elapsed}s</p>
                        </div>
                      </div>
                    </div>
                  )}
                  {!resultSuccess && !generatedChanges.length && (
                    <p className="text-sm text-muted-foreground mt-2" data-testid="text-result">{result}</p>
                  )}
                </CardContent>
              </Card>

              {(() => {
                const created = generatedChanges.filter(c => c.success && c.action === "create");
                const modified = generatedChanges.filter(c => c.success && c.action === "modify");
                const failed = generatedChanges.filter(c => !c.success);

                return (
                  <>
                    {created.length > 0 && (
                      <Card>
                        <CardHeader className="pb-2">
                          <CardTitle className="text-sm flex items-center gap-2">
                            <FilePlus className="h-4 w-4 text-success" />
                            New Files Created
                            <Badge variant="secondary" className="ml-1">{created.length}</Badge>
                          </CardTitle>
                        </CardHeader>
                        <CardContent className="pt-0">
                          <div className="divide-y divide-border">
                            {created.map((change, idx) => (
                              <div key={idx} className="flex items-start gap-3 py-2.5 first:pt-0 last:pb-0" data-testid={`row-created-${idx}`}>
                                <FileCode className="h-4 w-4 text-success shrink-0 mt-0.5" />
                                <div className="flex-1 min-w-0">
                                  <p className="text-sm font-mono font-medium truncate">{change.file_path}</p>
                                  <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">{change.description}</p>
                                </div>
                                <div className="flex items-center gap-1.5 shrink-0">
                                  {change.story_refs.map(ref => (
                                    <Badge key={ref} variant="outline" className="text-xs">{ref}</Badge>
                                  ))}
                                  {change.lines && (
                                    <span className="text-xs text-muted-foreground">{change.lines} lines</span>
                                  )}
                                </div>
                              </div>
                            ))}
                          </div>
                        </CardContent>
                      </Card>
                    )}

                    {modified.length > 0 && (
                      <Card>
                        <CardHeader className="pb-2">
                          <CardTitle className="text-sm flex items-center gap-2">
                            <FilePen className="h-4 w-4 text-primary" />
                            Files Modified
                            <Badge variant="secondary" className="ml-1">{modified.length}</Badge>
                          </CardTitle>
                        </CardHeader>
                        <CardContent className="pt-0">
                          <div className="divide-y divide-border">
                            {modified.map((change, idx) => (
                              <div key={idx} className="flex items-start gap-3 py-2.5 first:pt-0 last:pb-0" data-testid={`row-modified-${idx}`}>
                                <FileCode className="h-4 w-4 text-primary shrink-0 mt-0.5" />
                                <div className="flex-1 min-w-0">
                                  <p className="text-sm font-mono font-medium truncate">{change.file_path}</p>
                                  <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">{change.description}</p>
                                </div>
                                <div className="flex items-center gap-1.5 shrink-0">
                                  {change.story_refs.map(ref => (
                                    <Badge key={ref} variant="outline" className="text-xs">{ref}</Badge>
                                  ))}
                                  {change.lines && (
                                    <span className="text-xs text-muted-foreground">{change.lines} lines</span>
                                  )}
                                </div>
                              </div>
                            ))}
                          </div>
                        </CardContent>
                      </Card>
                    )}

                    {failed.length > 0 && (
                      <Card>
                        <CardHeader className="pb-2">
                          <CardTitle className="text-sm flex items-center gap-2">
                            <XCircle className="h-4 w-4 text-destructive" />
                            Failed
                            <Badge variant="destructive" className="ml-1">{failed.length}</Badge>
                          </CardTitle>
                        </CardHeader>
                        <CardContent className="pt-0">
                          <div className="divide-y divide-border">
                            {failed.map((change, idx) => (
                              <div key={idx} className="flex items-start gap-3 py-2.5 first:pt-0 last:pb-0" data-testid={`row-failed-${idx}`}>
                                <AlertCircle className="h-4 w-4 text-destructive shrink-0 mt-0.5" />
                                <div className="flex-1 min-w-0">
                                  <p className="text-sm font-mono font-medium truncate">{change.file_path}</p>
                                  <p className="text-xs text-destructive mt-0.5">{change.error || "Unknown error"}</p>
                                </div>
                              </div>
                            ))}
                          </div>
                        </CardContent>
                      </Card>
                    )}

                    {resultSuccess && generatedChanges.length > 0 && (
                      <div className="flex items-center gap-3 rounded-md border border-border bg-muted/30 px-4 py-3">
                        <GitBranch className="h-4 w-4 text-muted-foreground shrink-0" />
                        <p className="text-sm text-muted-foreground flex-1">
                          Ready to push. Create a new branch with these changes and open a pull request on GitHub.
                        </p>
                        <Button size="sm" onClick={() => setShowPushDialog(true)} data-testid="button-push-github-bottom">
                          <GitBranch className="h-3.5 w-3.5 mr-1.5" />
                          Push to GitHub
                        </Button>
                      </div>
                    )}
                  </>
                );
              })()}
            </div>
          )}

          {pushResult && (
            <Card data-testid="card-push-result">
              <CardContent className="py-4">
                <div className="flex items-start gap-3">
                  {pushResult.success ? (
                    <CheckCircle2 className="h-5 w-5 text-success shrink-0 mt-0.5" />
                  ) : (
                    <AlertCircle className="h-5 w-5 text-destructive shrink-0 mt-0.5" />
                  )}
                  <div className="min-w-0">
                    <p className="text-sm font-medium">{pushResult.message}</p>
                    {pushResult.pr_url && (
                      <a
                        href={pushResult.pr_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-sm text-primary underline flex items-center gap-1 mt-2"
                        data-testid="link-create-pr"
                      >
                        <ExternalLink className="h-3 w-3" />
                        Create Pull Request
                      </a>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {!result && !isGenerating && (
            <Card>
              <CardContent className="py-4">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <p className="text-sm text-muted-foreground">
                    The AI will analyze your repository's architecture, coding standards, and patterns
                    to generate code that integrates seamlessly with your codebase.
                  </p>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      </ScrollArea>

      <Dialog open={showPushDialog} onOpenChange={setShowPushDialog}>
        <DialogContent className="sm:max-w-md" data-testid="dialog-push-github">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <GitBranch className="h-5 w-5" />
              Push Code to GitHub
            </DialogTitle>
            <DialogDescription>
              Push the generated code to a new branch on your repository and create a pull request.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <Label htmlFor="codegen-github-token">GitHub Personal Access Token</Label>
              <Input
                id="codegen-github-token"
                type="password"
                value={pushToken}
                onChange={(e) => setPushToken(e.target.value)}
                placeholder="ghp_xxxxxxxxxxxx"
                data-testid="input-github-token"
              />
              <p className="text-xs text-muted-foreground">
                Leave empty to use the server-configured token. Needs <strong>repo</strong> scope permissions.
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="codegen-branch-name">Branch Name</Label>
              <Input
                id="codegen-branch-name"
                value={pushBranch}
                onChange={(e) => setPushBranch(e.target.value)}
                placeholder="ai-generated-code"
                data-testid="input-branch-name"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="codegen-commit-msg">Commit Message</Label>
              <Input
                id="codegen-commit-msg"
                value={pushCommitMsg}
                onChange={(e) => setPushCommitMsg(e.target.value)}
                placeholder="feat: AI-generated code implementation"
                data-testid="input-commit-message"
              />
            </div>
          </div>
          <DialogFooter className="flex gap-2">
            <Button variant="outline" onClick={() => setShowPushDialog(false)} data-testid="button-cancel-push">
              Cancel
            </Button>
            <Button onClick={handlePushToGitHub} disabled={isPushing} data-testid="button-confirm-push">
              {isPushing ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  Pushing...
                </>
              ) : (
                <>
                  <GitBranch className="h-4 w-4 mr-2" />
                  Push to GitHub
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
