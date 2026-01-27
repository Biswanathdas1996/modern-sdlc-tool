import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Link, useLocation } from "wouter";
import { ArrowLeft, ArrowRight, Bookmark, RefreshCw, Clock, Layers, Tag, CheckCircle2, AlertCircle, Loader2, Wand2, Copy, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { EmptyState } from "@/components/EmptyState";
import { apiRequest, queryClient } from "@/lib/queryClient";
import type { BRD, UserStory } from "@shared/schema";

export default function UserStoriesPage() {
  const [, navigate] = useLocation();
  const [isGeneratingTests, setIsGeneratingTests] = useState(false);
  const [copilotPrompt, setCopilotPrompt] = useState<string | null>(null);
  const [promptDialogOpen, setPromptDialogOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  const { data: brd, isLoading: brdLoading } = useQuery<BRD>({
    queryKey: ["/api/brd/current"],
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

  const generateStoriesMutation = useMutation({
    mutationFn: async () => {
      const response = await apiRequest("POST", "/api/user-stories/generate");
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/user-stories", brd?.id] });
    },
  });

  const generateTestCasesMutation = useMutation({
    mutationFn: async () => {
      setIsGeneratingTests(true);
      const response = await apiRequest("POST", "/api/test-cases/generate");
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/test-cases"] });
      setIsGeneratingTests(false);
      navigate("/test-cases");
    },
    onError: () => {
      setIsGeneratingTests(false);
    },
  });

  const generatePromptMutation = useMutation({
    mutationFn: async () => {
      const response = await apiRequest("POST", "/api/copilot-prompt/generate");
      return response.json();
    },
    onSuccess: (data) => {
      setCopilotPrompt(data.prompt);
      setPromptDialogOpen(true);
    },
  });

  const copyToClipboard = async () => {
    if (copilotPrompt) {
      await navigator.clipboard.writeText(copilotPrompt);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const isLoading = brdLoading || storiesLoading;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  if (!brd) {
    return (
      <div className="container max-w-4xl mx-auto py-8 px-4">
        <EmptyState
          icon="document"
          title="No BRD Available"
          description="Generate a Business Requirements Document first before creating user stories."
          action={{
            label: "Go to BRD",
            onClick: () => window.location.href = "/brd",
          }}
        />
      </div>
    );
  }

  return (
    <div className="container max-w-6xl mx-auto py-8 px-4 h-full overflow-auto">
      <div className="flex items-center justify-between gap-4 mb-6 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
            <Bookmark className="h-6 w-6 text-primary" />
            User Stories for JIRA
          </h1>
          <p className="text-muted-foreground mt-1">
            JIRA-style user stories generated from your BRD and repository documentation
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {userStories && userStories.length > 0 && (
            <Dialog open={promptDialogOpen} onOpenChange={setPromptDialogOpen}>
              <DialogTrigger asChild>
                <Button
                  variant="outline"
                  onClick={() => generatePromptMutation.mutate()}
                  disabled={generatePromptMutation.isPending}
                  data-testid="button-generate-prompt"
                >
                  {generatePromptMutation.isPending ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      Generating Prompt...
                    </>
                  ) : (
                    <>
                      <Wand2 className="h-4 w-4 mr-2" />
                      Prompt
                    </>
                  )}
                </Button>
              </DialogTrigger>
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
                <div className="flex justify-end mb-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={copyToClipboard}
                    data-testid="button-copy-prompt"
                  >
                    {copied ? (
                      <>
                        <Check className="h-4 w-4 mr-2 text-success" />
                        Copied!
                      </>
                    ) : (
                      <>
                        <Copy className="h-4 w-4 mr-2" />
                        Copy to Clipboard
                      </>
                    )}
                  </Button>
                </div>
                <ScrollArea className="h-[60vh] rounded-md border p-4">
                  <pre className="text-sm whitespace-pre-wrap font-mono text-foreground">
                    {copilotPrompt || "Loading..."}
                  </pre>
                </ScrollArea>
              </DialogContent>
            </Dialog>
          )}
          <Button
            onClick={() => generateStoriesMutation.mutate()}
            disabled={generateStoriesMutation.isPending}
            data-testid="button-generate-stories"
          >
            {generateStoriesMutation.isPending ? (
              <>
                <LoadingSpinner size="sm" className="mr-2" />
                Generating...
              </>
            ) : userStories && userStories.length > 0 ? (
              <>
                <RefreshCw className="h-4 w-4 mr-2" />
                Regenerate Stories
              </>
            ) : (
              <>
                <Bookmark className="h-4 w-4 mr-2" />
                Generate User Stories
              </>
            )}
          </Button>
        </div>
      </div>

      {generateStoriesMutation.isError && (
        <Card className="mb-6 border-destructive">
          <CardContent className="py-4">
            <div className="flex items-center gap-2 text-destructive">
              <AlertCircle className="h-5 w-5" />
              <span>Failed to generate user stories. Please try again.</span>
            </div>
          </CardContent>
        </Card>
      )}

      {userStories && userStories.length > 0 ? (
        <div className="space-y-4">
          <div className="flex items-center justify-between text-sm text-muted-foreground mb-4">
            <span>{userStories.length} user {userStories.length === 1 ? 'story' : 'stories'} generated</span>
            <span>Based on: {brd.title}</span>
          </div>

          {userStories.map((story) => (
            <Card
              key={story.id}
              className="hover-elevate"
              data-testid={`card-user-story-${story.storyKey}`}
            >
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between gap-2 flex-wrap">
                  <div className="flex items-center gap-2 flex-wrap">
                    <Badge variant="outline" className="font-mono text-xs" data-testid={`badge-story-key-${story.storyKey}`}>
                      {story.storyKey}
                    </Badge>
                    <Badge
                      variant={
                        story.priority === "highest" || story.priority === "high"
                          ? "destructive"
                          : story.priority === "medium"
                          ? "default"
                          : "secondary"
                      }
                      data-testid={`badge-priority-${story.storyKey}`}
                    >
                      {story.priority}
                    </Badge>
                    {story.storyPoints && (
                      <Badge variant="outline" className="flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        {story.storyPoints} pts
                      </Badge>
                    )}
                  </div>
                  {story.epic && (
                    <Badge variant="secondary" className="flex items-center gap-1">
                      <Layers className="h-3 w-3" />
                      {story.epic}
                    </Badge>
                  )}
                </div>
                <CardTitle className="text-lg mt-2" data-testid={`text-story-title-${story.storyKey}`}>
                  {story.title}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="p-3 rounded-md bg-muted/50">
                  <p className="text-sm">
                    <span className="font-medium text-foreground">As a</span>{" "}
                    <span className="text-muted-foreground">{story.asA},</span>{" "}
                    <span className="font-medium text-foreground">I want</span>{" "}
                    <span className="text-muted-foreground">{story.iWant},</span>{" "}
                    <span className="font-medium text-foreground">so that</span>{" "}
                    <span className="text-muted-foreground">{story.soThat}</span>
                  </p>
                </div>

                {story.description && (
                  <p className="text-sm text-muted-foreground">{story.description}</p>
                )}

                {story.acceptanceCriteria.length > 0 && (
                  <div>
                    <p className="text-xs font-medium text-muted-foreground mb-2">
                      Acceptance Criteria:
                    </p>
                    <ul className="space-y-1.5">
                      {story.acceptanceCriteria.map((criteria, i) => (
                        <li key={i} className="flex items-start gap-2 text-sm">
                          <CheckCircle2 className="h-4 w-4 text-success shrink-0 mt-0.5" />
                          <span className="text-foreground">{criteria}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {story.technicalNotes && (
                  <div className="p-3 rounded-md bg-accent/10 border border-accent/20">
                    <p className="text-xs font-medium text-accent mb-1">Technical Notes:</p>
                    <p className="text-sm text-foreground">{story.technicalNotes}</p>
                  </div>
                )}

                <div className="flex items-center gap-2 flex-wrap">
                  {story.labels.map((label, i) => (
                    <Badge key={i} variant="outline" className="text-xs flex items-center gap-1">
                      <Tag className="h-3 w-3" />
                      {label}
                    </Badge>
                  ))}
                </div>

                {story.dependencies.length > 0 && (
                  <div className="pt-3 border-t">
                    <p className="text-xs text-muted-foreground">
                      <span className="font-medium">Dependencies:</span>{" "}
                      {story.dependencies.join(", ")}
                    </p>
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <EmptyState
          icon="default"
          title="No User Stories Yet"
          description="Generate JIRA-style user stories from your BRD to break down the requirements into actionable development tasks."
          action={{
            label: "Generate User Stories",
            onClick: () => generateStoriesMutation.mutate(),
          }}
        />
      )}

      <div className="flex justify-between mt-8 pt-4 border-t gap-4 flex-wrap">
        <Link href="/brd">
          <Button variant="outline" data-testid="button-back-to-brd" disabled={generateTestCasesMutation.isPending}>
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back to BRD
          </Button>
        </Link>
        <Button 
          onClick={() => generateTestCasesMutation.mutate()}
          disabled={generateTestCasesMutation.isPending || !brd}
          data-testid="button-next-test-cases"
        >
          {generateTestCasesMutation.isPending ? (
            <>
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              Generating Test Cases...
            </>
          ) : (
            <>
              Generate Test Cases
              <ArrowRight className="h-4 w-4 ml-2" />
            </>
          )}
        </Button>
      </div>
    </div>
  );
}
