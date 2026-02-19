import { useState, useRef, useEffect } from "react";
import { useMutation } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { User, Send, Shield, RefreshCw, MessageSquare, ChevronDown, ChevronRight, Copy, Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiRequest } from "@/lib/queryClient";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  thinking_steps?: Array<{ type: string; content: string; tool_name?: string }>;
}

function generateSessionId(): string {
  return crypto.randomUUID();
}

function formatSecurityReport(content: string): string {
  const lines = content.split("\n");
  const html: string[] = [];
  let inCodeBlock = false;
  let codeLines: string[] = [];
  let inTable = false;
  let tableRows: string[] = [];
  let isFirstTableRow = true;

  const flushTable = () => {
    if (tableRows.length > 0) {
      html.push('<div class="sec-table-wrap"><table class="sec-table">');
      html.push(tableRows.join(""));
      html.push("</table></div>");
      tableRows = [];
      inTable = false;
      isFirstTableRow = true;
    }
  };

  const escapeHtml = (text: string) =>
    text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

  const inlineFormat = (text: string): string => {
    return text
      .replace(/\*\*`([^`]+)`\*\*/g, '<strong><code class="sec-code">$1</code></strong>')
      .replace(/`([^`]+)`/g, '<code class="sec-code">$1</code>')
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\*(.+?)\*/g, "<em>$1</em>")
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer" class="sec-link">$1</a>');
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    if (trimmed.startsWith("```")) {
      if (inCodeBlock) {
        html.push('<div class="sec-codeblock"><pre><code>' + escapeHtml(codeLines.join("\n")) + "</code></pre></div>");
        codeLines = [];
        inCodeBlock = false;
      } else {
        flushTable();
        inCodeBlock = true;
      }
      continue;
    }

    if (inCodeBlock) {
      codeLines.push(line);
      continue;
    }

    if (trimmed.startsWith("|") && trimmed.endsWith("|")) {
      if (trimmed.replace(/[|\s-:]/g, "") === "") {
        continue;
      }
      if (!inTable) {
        flushTable();
        inTable = true;
        isFirstTableRow = true;
      }
      const cells = trimmed
        .slice(1, -1)
        .split("|")
        .map((c) => c.trim());
      const tag = isFirstTableRow ? "th" : "td";
      const rowClass = isFirstTableRow ? "sec-thead-row" : "sec-tbody-row";
      tableRows.push(
        `<tr class="${rowClass}">${cells.map((c) => `<${tag}>${inlineFormat(c)}</${tag}>`).join("")}</tr>`
      );
      isFirstTableRow = false;
      continue;
    } else if (inTable) {
      flushTable();
    }

    if (trimmed === "---" || trimmed === "***" || trimmed === "___") {
      html.push('<hr class="sec-hr" />');
      continue;
    }

    if (trimmed === "") {
      continue;
    }

    if (trimmed.startsWith("# ")) {
      const text = trimmed.slice(2);
      const isReport = text.includes("Security Assessment Report");
      if (isReport) {
        html.push(`<div class="sec-report-header"><div class="sec-report-icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg></div><h1 class="sec-h1">${inlineFormat(text.replace(/🛡️\s*/, ""))}</h1></div>`);
      } else {
        html.push(`<h1 class="sec-h1">${inlineFormat(text)}</h1>`);
      }
      continue;
    }

    if (trimmed.startsWith("## ")) {
      const text = trimmed.slice(3);
      const iconMap: Record<string, string> = {
        "Risk Overview": "bar-chart",
        "Detailed Findings": "alert-triangle",
        "Reconnaissance Data": "search",
        "Source Code Analysis": "folder",
        "Methodology": "layers",
        "Assessment Limitations": "alert-circle",
      };
      let iconSvg = "";
      for (const [key, icon] of Object.entries(iconMap)) {
        if (text.includes(key)) {
          iconSvg = `<span class="sec-section-icon sec-icon-${icon}"></span>`;
          break;
        }
      }
      html.push(`<h2 class="sec-h2">${iconSvg}${inlineFormat(text.replace(/[🔍📂⚠️]/g, "").trim())}</h2>`);
      continue;
    }

    if (trimmed.startsWith("### ")) {
      const text = trimmed.slice(4);
      const severityMatch = text.match(/^(🔴|🟠|🟡|🔵|⚪)\s*#(\d+)\s*—\s*(.+)/);
      if (severityMatch) {
        const [, icon, num, title] = severityMatch;
        const severityMap: Record<string, string> = {
          "🔴": "critical",
          "🟠": "high",
          "🟡": "medium",
          "🔵": "low",
          "⚪": "info",
        };
        const sev = severityMap[icon] || "info";
        html.push(`<div class="sec-finding sec-finding-${sev}"><div class="sec-finding-header"><span class="sec-finding-num">#${num}</span><span class="sec-finding-title">${inlineFormat(title)}</span></div>`);
        const endIdx = findFindingEnd(lines, i + 1);
        const findingLines = lines.slice(i + 1, endIdx);
        html.push(renderFindingBody(findingLines, inlineFormat, escapeHtml));
        html.push("</div>");
        i = endIdx - 1;
        continue;
      }

      const headerMatch = text.match(/^(.+?)(?:\s*\((\d+)\s*found\))?$/);
      if (headerMatch) {
        html.push(`<h3 class="sec-h3">${inlineFormat(text.replace(/[❌✅⚠️🟢🔴🟠🟡🔵⚪]/g, "").trim())}</h3>`);
      } else {
        html.push(`<h3 class="sec-h3">${inlineFormat(text)}</h3>`);
      }
      continue;
    }

    if (trimmed.startsWith("> ")) {
      const quoteContent = trimmed.slice(2);
      const riskMatch = quoteContent.match(/^(🔴|🟠|🟡|🔵|🟢|⚠️)\s*\*\*Overall Risk:\s*(CRITICAL|HIGH|MEDIUM|LOW|PASS|INCONCLUSIVE)\*\*/);
      if (riskMatch) {
        const [, , level] = riskMatch;
        const riskClass = level.toLowerCase();
        html.push(`<div class="sec-risk-banner sec-risk-${riskClass}"><div class="sec-risk-level">${level}</div><div class="sec-risk-detail">${inlineFormat(quoteContent.replace(/^(🔴|🟠|🟡|🔵|🟢|⚠️)\s*/, "").replace(/\*\*Overall Risk:\s*(CRITICAL|HIGH|MEDIUM|LOW|PASS|INCONCLUSIVE)\*\*\s*—\s*/, ""))}</div></div>`);
      } else if (quoteContent.includes("Remediation:") || quoteContent.includes("💡")) {
        html.push(`<div class="sec-remediation">${inlineFormat(quoteContent.replace(/💡\s*/, ""))}</div>`);
      } else if (quoteContent.includes("Evidence Policy")) {
        html.push(`<div class="sec-policy">${inlineFormat(quoteContent)}</div>`);
      } else if (quoteContent.includes("🟢")) {
        html.push(`<div class="sec-pass-banner">${inlineFormat(quoteContent.replace(/🟢\s*/, ""))}</div>`);
      } else {
        html.push(`<blockquote class="sec-blockquote">${inlineFormat(quoteContent)}</blockquote>`);
      }
      continue;
    }

    if (trimmed.startsWith("- ")) {
      const items: string[] = [trimmed.slice(2)];
      while (i + 1 < lines.length && lines[i + 1].trim().startsWith("- ")) {
        i++;
        items.push(lines[i].trim().slice(2));
      }
      html.push('<ul class="sec-list">');
      for (const item of items) {
        const hasCheck = item.includes("✅");
        const hasWarn = item.includes("⚠️") || item.includes("❌");
        const cls = hasCheck ? "sec-list-ok" : hasWarn ? "sec-list-warn" : "";
        html.push(`<li class="${cls}">${inlineFormat(item.replace(/[✅❌⚠️]/g, "").trim())}</li>`);
      }
      html.push("</ul>");
      continue;
    }

    if (trimmed.match(/^\d+\.\s/)) {
      const items: string[] = [trimmed.replace(/^\d+\.\s/, "")];
      while (i + 1 < lines.length && lines[i + 1].trim().match(/^\d+\.\s/)) {
        i++;
        items.push(lines[i].trim().replace(/^\d+\.\s/, ""));
      }
      html.push('<ol class="sec-olist">');
      for (const item of items) {
        html.push(`<li>${inlineFormat(item)}</li>`);
      }
      html.push("</ol>");
      continue;
    }

    if (trimmed.startsWith("**Scan Coverage:**") || trimmed.startsWith("**Evidence:**") || trimmed.startsWith("**Location:**")) {
      html.push(`<div class="sec-meta">${inlineFormat(trimmed)}</div>`);
      continue;
    }

    html.push(`<p class="sec-p">${inlineFormat(trimmed)}</p>`);
  }

  flushTable();
  return html.join("");
}

function findFindingEnd(lines: string[], startIdx: number): number {
  for (let i = startIdx; i < lines.length; i++) {
    const trimmed = lines[i].trim();
    if (trimmed === "---" || trimmed === "***" || trimmed === "___") {
      return i + 1;
    }
    if (trimmed.startsWith("### ") && i > startIdx) {
      return i;
    }
    if (trimmed.startsWith("## ")) {
      return i;
    }
  }
  return lines.length;
}

function renderFindingBody(lines: string[], inlineFormat: (s: string) => string, escapeHtml: (s: string) => string): string {
  const parts: string[] = [];
  let inCode = false;
  let codeLines: string[] = [];

  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed === "" || trimmed === "---") continue;

    if (trimmed.startsWith("```")) {
      if (inCode) {
        parts.push('<div class="sec-codeblock sec-codeblock-sm"><pre><code>' + escapeHtml(codeLines.join("\n")) + "</code></pre></div>");
        codeLines = [];
        inCode = false;
      } else {
        inCode = true;
      }
      continue;
    }
    if (inCode) {
      codeLines.push(line);
      continue;
    }

    if (trimmed.startsWith("> ") && (trimmed.includes("Remediation") || trimmed.includes("💡"))) {
      parts.push(`<div class="sec-remediation">${inlineFormat(trimmed.slice(2).replace(/💡\s*/, ""))}</div>`);
      continue;
    }

    if (trimmed.startsWith("**`") && trimmed.includes("·")) {
      const badgeMatch = trimmed.match(/\*\*`([^`]+)`\*\*\s*·\s*(.*)/);
      if (badgeMatch) {
        const [, severity, owasp] = badgeMatch;
        const sevLower = severity.toLowerCase();
        parts.push(`<div class="sec-finding-meta"><span class="sec-severity-badge sec-sev-${sevLower}">${severity}</span><span class="sec-owasp-tag">${inlineFormat(owasp)}</span></div>`);
        continue;
      }
    }

    if (trimmed.startsWith("**Location:**")) {
      parts.push(`<div class="sec-finding-location">${inlineFormat(trimmed)}</div>`);
      continue;
    }

    if (trimmed.startsWith("**Evidence:**")) {
      parts.push(`<div class="sec-finding-evidence">${inlineFormat(trimmed)}</div>`);
      continue;
    }

    if (trimmed.startsWith("**📸")) {
      parts.push(`<div class="sec-snapshot-label">${inlineFormat(trimmed)}</div>`);
      continue;
    }

    parts.push(`<p class="sec-finding-desc">${inlineFormat(trimmed)}</p>`);
  }

  return parts.join("");
}

export default function SecurityAgentPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState(() => generateSessionId());
  const [expandedSteps, setExpandedSteps] = useState<Record<string, boolean>>({});
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    document.title = "Shannon Security Agent | DocuGen AI";
  }, []);

  const chatMutation = useMutation({
    mutationFn: async (prompt: string) => {
      const response = await apiRequest("POST", "/api/v1/security-agent/chat", {
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
      };
      setMessages((prev) => [...prev, assistantMessage]);
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
    setExpandedSteps({});
  };

  const toggleSteps = (msgId: string) => {
    setExpandedSteps((prev) => ({ ...prev, [msgId]: !prev[msgId] }));
  };

  return (
    <div className="h-full flex flex-col overflow-hidden">
      <div className="flex-none p-6 pb-0">
        <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-destructive">
              <Shield className="h-5 w-5 text-destructive-foreground" />
            </div>
            <div>
              <h1 className="text-2xl font-bold" data-testid="text-page-title">Shannon Security Agent</h1>
              <p className="text-sm text-muted-foreground">
                AI-powered web application security assessment
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
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

      <div className="flex-1 min-h-0 p-6 pt-4 overflow-hidden">
        <Card className="h-full flex flex-col">
          <CardHeader className="flex-none pb-3 border-b">
            <CardTitle className="text-base flex items-center gap-2">
              <MessageSquare className="h-4 w-4" />
              Security Assessment
            </CardTitle>
          </CardHeader>
          <CardContent className="flex-1 min-h-0 flex flex-col p-0 overflow-hidden">
            <div className="flex-1 min-h-0 overflow-y-auto p-4" data-testid="container-messages">
              {messages.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center text-center py-12">
                  <div className="flex h-16 w-16 items-center justify-center rounded-full bg-muted mb-4">
                    <Shield className="h-8 w-8 text-muted-foreground" />
                  </div>
                  <h3 className="text-lg font-medium mb-2">Security Assessment</h3>
                  <p className="text-sm text-muted-foreground max-w-md">
                    Provide a URL to perform a deep AI-driven security assessment including
                    OWASP Top 10 analysis, injection testing, and vulnerability scanning.
                  </p>
                  <div className="mt-6 flex flex-wrap gap-2 justify-center">
                    {[
                      "Scan https://example.com for vulnerabilities",
                      "What security checks do you perform?",
                      "Run an OWASP assessment",
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
                        "flex h-8 w-8 shrink-0 items-center justify-center rounded-full mt-1",
                        message.role === "user" ? "bg-primary text-primary-foreground" : "bg-muted"
                      )}>
                        {message.role === "user" ? <User className="h-4 w-4" /> : <Shield className="h-4 w-4" />}
                      </div>
                      <div className={cn("flex flex-col min-w-0", message.role === "user" ? "items-end max-w-[80%]" : "items-start flex-1")}>
                        <div className={cn(
                          "rounded-xl w-full",
                          message.role === "user"
                            ? "bg-primary text-primary-foreground px-4 py-2.5 w-auto"
                            : "sec-report-container"
                        )}>
                          {message.role === "user" ? (
                            <p className="text-sm whitespace-pre-wrap">{message.content}</p>
                          ) : (
                            <div className="sec-report" dangerouslySetInnerHTML={{ __html: formatSecurityReport(message.content) }} />
                          )}
                        </div>
                        {message.thinking_steps && message.thinking_steps.length > 0 && (
                          <div className="mt-2 w-full">
                            <button
                              onClick={() => toggleSteps(message.id)}
                              className="flex items-center gap-1.5 text-xs text-muted-foreground hover-elevate rounded-md px-2 py-1"
                              data-testid={`button-toggle-steps-${index}`}
                            >
                              {expandedSteps[message.id] ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                              {message.thinking_steps.length} scan phases
                            </button>
                            {expandedSteps[message.id] && (
                              <div className="mt-1.5 space-y-1 pl-2 border-l-2 border-border/50">
                                {message.thinking_steps.map((step, i) => (
                                  <div key={i} className="flex items-start gap-2 text-xs text-muted-foreground py-0.5" data-testid={`step-${index}-${i}`}>
                                    <Badge variant="outline" className="text-[10px] shrink-0 px-1.5 py-0">
                                      {step.tool_name || step.type}
                                    </Badge>
                                    <span className="break-words">{step.content}</span>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )}
                        <span className="text-xs text-muted-foreground mt-1">{message.timestamp.toLocaleTimeString()}</span>
                      </div>
                    </div>
                  ))}
                  {chatMutation.isPending && (
                    <div className="flex gap-3" data-testid="loading-indicator">
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-muted">
                        <Shield className="h-4 w-4" />
                      </div>
                      <div className="flex items-center gap-2 rounded-lg bg-muted px-4 py-2">
                        <LoadingSpinner size="sm" />
                        <span className="text-sm text-muted-foreground">Running security scan...</span>
                      </div>
                    </div>
                  )}
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
                  placeholder="Enter a URL to scan or ask about security... (Press Enter to send)"
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
