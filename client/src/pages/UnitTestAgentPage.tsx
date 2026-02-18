import { useState, useRef, useEffect } from "react";
import { useMutation } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { Bot, User, Send, FlaskConical, RefreshCw, MessageSquare } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiRequest } from "@/lib/queryClient";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  thinking_steps?: Array<{ type: string; content: string; tool_name?: string }>;
  task_id?: string;
}

function generateSessionId(): string {
  return crypto.randomUUID();
}

function formatMarkdown(content: string): string {
  return content
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.+<\/li>\n?)+/g, '<ul>$&</ul>')
    .replace(/^\d+\. (.+)$/gm, '<li>$1</li>')
    .replace(/\n\n/g, '<br/><br/>')
    .replace(/\n/g, '<br/>');
}

export default function UnitTestAgentPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState(() => generateSessionId());
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    document.title = "Unit Test Agent | DocuGen AI";
  }, []);

  const chatMutation = useMutation({
    mutationFn: async (prompt: string) => {
      const response = await apiRequest("POST", "/api/v1/unit-test-agent/chat", {
        prompt,
        session_id: sessionId,
      });
      return response.json();
    },
    onSuccess: (data) => {
      const assistantMessage: Message = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: data.response || data.message || JSON.stringify(data, null, 2),
        timestamp: new Date(),
        thinking_steps: data.thinking_steps,
        task_id: data.task_id,
      };
      setMessages((prev) => [...prev, assistantMessage]);
      if (data.task_id) {
        setActiveTaskId(data.task_id);
      }
    },
    onError: (error: Error) => {
      const errorMessage: Message = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: `Error: ${error.message}`,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    },
  });

  const pollTaskMutation = useMutation({
    mutationFn: async (taskId: string) => {
      const response = await apiRequest("GET", `/api/v1/unit-test-agent/task/${taskId}`);
      return response.json();
    },
    onSuccess: (data) => {
      if ((data.status === "completed" || data.status === "failed") && data.response) {
        setActiveTaskId(null);
        const resultMessage: Message = {
          id: crypto.randomUUID(),
          role: "assistant",
          content: data.response,
          timestamp: new Date(),
          thinking_steps: data.thinking_steps,
        };
        setMessages((prev) => [...prev, resultMessage]);
      } else if (data.status === "failed" || data.status === "error") {
        setActiveTaskId(null);
        const errorMsg: Message = {
          id: crypto.randomUUID(),
          role: "assistant",
          content: data.response || "Task failed unexpectedly.",
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, errorMsg]);
      }
    },
    onError: () => {
      setActiveTaskId(null);
      const errorMsg: Message = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: "Lost connection while polling task status. Please try again.",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMsg]);
    },
  });

  useEffect(() => {
    if (!activeTaskId) return;
    let pollCount = 0;
    const maxPolls = 120;
    const interval = setInterval(() => {
      pollCount++;
      if (pollCount >= maxPolls) {
        clearInterval(interval);
        setActiveTaskId(null);
        const timeoutMsg: Message = {
          id: crypto.randomUUID(),
          role: "assistant",
          content: "Task polling timed out after 10 minutes. The task may still be running in the background.",
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, timeoutMsg]);
        return;
      }
      pollTaskMutation.mutate(activeTaskId);
    }, 5000);
    return () => clearInterval(interval);
  }, [activeTaskId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || chatMutation.isPending) return;
    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: input.trim(),
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMessage]);
    chatMutation.mutate(input.trim());
    setInput("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const handleNewSession = () => {
    setSessionId(generateSessionId());
    setMessages([]);
    setActiveTaskId(null);
  };

  return (
    <div className="h-full flex flex-col overflow-hidden">
      <div className="flex-none p-6 pb-0">
        <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-success">
              <FlaskConical className="h-5 w-5 text-success-foreground" />
            </div>
            <div>
              <h1 className="text-2xl font-bold" data-testid="text-page-title">Unit Test Agent</h1>
              <p className="text-sm text-muted-foreground">
                AI-powered unit test generation with auto-validation
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {activeTaskId && (
              <Badge variant="secondary" className="text-xs" data-testid="badge-task-running">
                <LoadingSpinner size="sm" />
                <span className="ml-1">Generating tests...</span>
              </Badge>
            )}
            <Badge variant="outline" className="font-mono text-xs" data-testid="badge-session-id">
              Session: {sessionId.slice(0, 8)}...
            </Badge>
            <Button variant="outline" size="sm" onClick={handleNewSession} data-testid="button-new-session">
              <RefreshCw className="h-4 w-4 mr-2" />
              New Session
            </Button>
          </div>
        </div>
      </div>

      <div className="flex-1 p-6 pt-4 overflow-hidden">
        <Card className="h-full flex flex-col">
          <CardHeader className="flex-none pb-3 border-b">
            <CardTitle className="text-base flex items-center gap-2">
              <MessageSquare className="h-4 w-4" />
              Test Generation
            </CardTitle>
          </CardHeader>
          <CardContent className="flex-1 flex flex-col p-0 overflow-hidden">
            <div className="flex-1 overflow-y-auto p-4" data-testid="container-messages">
              {messages.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center text-center py-12">
                  <div className="flex h-16 w-16 items-center justify-center rounded-full bg-muted mb-4">
                    <FlaskConical className="h-8 w-8 text-muted-foreground" />
                  </div>
                  <h3 className="text-lg font-medium mb-2">Unit Test Generation</h3>
                  <p className="text-sm text-muted-foreground max-w-md">
                    Generate intelligent unit tests for your repository. The agent scans your code,
                    identifies coverage gaps, generates tests, and validates them by running each one.
                  </p>
                  <div className="mt-6 flex flex-wrap gap-2 justify-center">
                    {[
                      "Generate tests for my repo",
                      "Check test generation status",
                      "What testing frameworks do you support?",
                    ].map((suggestion) => (
                      <Button
                        key={suggestion}
                        variant="outline"
                        size="sm"
                        onClick={() => setInput(suggestion)}
                        data-testid={`button-suggestion-${suggestion.slice(0, 20).toLowerCase().replace(/\s+/g, "-")}`}
                      >
                        {suggestion}
                      </Button>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  {messages.map((message, index) => (
                    <div
                      key={message.id}
                      data-testid={`message-${message.role}-${index}`}
                      className={cn("flex gap-3", message.role === "user" ? "flex-row-reverse" : "flex-row")}
                    >
                      <div className={cn(
                        "flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
                        message.role === "user" ? "bg-primary text-primary-foreground" : "bg-muted"
                      )}>
                        {message.role === "user" ? <User className="h-4 w-4" /> : <FlaskConical className="h-4 w-4" />}
                      </div>
                      <div className={cn("flex flex-col max-w-[80%]", message.role === "user" ? "items-end" : "items-start")}>
                        <div className={cn(
                          "rounded-xl",
                          message.role === "user"
                            ? "bg-primary text-primary-foreground px-4 py-2.5"
                            : "bg-gradient-to-br from-card to-muted/30 border border-border/50 px-5 py-4 shadow-sm"
                        )}>
                          {message.role === "user" ? (
                            <p className="text-sm whitespace-pre-wrap">{message.content}</p>
                          ) : (
                            <div className="prose-chat text-sm" dangerouslySetInnerHTML={{ __html: formatMarkdown(message.content) }} />
                          )}
                        </div>
                        {message.thinking_steps && message.thinking_steps.length > 0 && (
                          <div className="mt-1 flex flex-wrap gap-1">
                            {message.thinking_steps.map((step, i) => (
                              <Badge key={i} variant="outline" className="text-xs" data-testid={`badge-step-${index}-${i}`}>
                                {step.tool_name || step.type}: {step.content.slice(0, 50)}
                              </Badge>
                            ))}
                          </div>
                        )}
                        <span className="text-xs text-muted-foreground mt-1">{message.timestamp.toLocaleTimeString()}</span>
                      </div>
                    </div>
                  ))}
                  {chatMutation.isPending && (
                    <div className="flex gap-3" data-testid="loading-indicator">
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-muted">
                        <FlaskConical className="h-4 w-4" />
                      </div>
                      <div className="flex items-center gap-2 rounded-lg bg-muted px-4 py-2">
                        <LoadingSpinner size="sm" />
                        <span className="text-sm text-muted-foreground">Processing...</span>
                      </div>
                    </div>
                  )}
                  <div ref={messagesEndRef} />
                </div>
              )}
            </div>

            <div className="flex-none p-4 border-t">
              <form onSubmit={handleSubmit} className="flex gap-2">
                <Textarea
                  ref={textareaRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Ask about unit tests or generate tests... (Press Enter to send)"
                  className="resize-none"
                  rows={2}
                  disabled={chatMutation.isPending}
                  data-testid="input-chat-message"
                />
                <Button type="submit" disabled={!input.trim() || chatMutation.isPending} data-testid="button-send-message">
                  <Send className="h-4 w-4" />
                </Button>
              </form>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
