import { FileText, Download, Copy, Check, ExternalLink } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";

interface DocumentPreviewProps {
  title: string;
  content: string;
  type: "brd" | "documentation" | "test-case" | "test-data";
  status?: "draft" | "review" | "approved";
  version?: string;
  onExport?: () => void;
  className?: string;
}

export function DocumentPreview({
  title,
  content,
  type,
  status,
  version,
  onExport,
  className,
}: DocumentPreviewProps) {
  const [copied, setCopied] = useState(false);

  const copyToClipboard = async () => {
    await navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const getTypeColor = () => {
    switch (type) {
      case "brd":
        return "bg-primary/10 text-primary border-primary/30";
      case "documentation":
        return "bg-accent/10 text-accent border-accent/30";
      case "test-case":
        return "bg-success/10 text-success border-success/30";
      case "test-data":
        return "bg-warning/10 text-warning border-warning/30";
    }
  };

  const getStatusColor = () => {
    switch (status) {
      case "draft":
        return "bg-muted text-muted-foreground";
      case "review":
        return "bg-warning/10 text-warning";
      case "approved":
        return "bg-success/10 text-success";
      default:
        return "";
    }
  };

  return (
    <Card className={cn("flex flex-col h-full", className)}>
      <CardHeader className="flex-shrink-0 flex flex-row items-start justify-between gap-4 space-y-0 pb-3">
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2 flex-wrap">
            <FileText className="h-5 w-5 text-muted-foreground" />
            <CardTitle className="text-lg">{title}</CardTitle>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant="outline" className={cn("text-xs", getTypeColor())}>
              {type.toUpperCase()}
            </Badge>
            {version && (
              <Badge variant="outline" className="text-xs">
                v{version}
              </Badge>
            )}
            {status && (
              <Badge variant="outline" className={cn("text-xs capitalize", getStatusColor())}>
                {status}
              </Badge>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            onClick={copyToClipboard}
            data-testid="button-copy-document"
          >
            {copied ? (
              <Check className="h-4 w-4 text-success" />
            ) : (
              <Copy className="h-4 w-4" />
            )}
          </Button>
          {onExport && (
            <Button
              variant="ghost"
              size="icon"
              onClick={onExport}
              data-testid="button-export-document"
            >
              <Download className="h-4 w-4" />
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="flex-1 overflow-hidden p-0">
        <ScrollArea className="h-full">
          <div className="prose-docs px-6 pb-6">
            <div dangerouslySetInnerHTML={{ __html: formatContent(content) }} />
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}

function formatContent(content: string): string {
  // Simple markdown-like formatting
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
    .replace(/\n\n/g, '</p><p>')
    .replace(/^(.+)$/gm, (match) => {
      if (match.startsWith('<')) return match;
      return `<p>${match}</p>`;
    });
}
