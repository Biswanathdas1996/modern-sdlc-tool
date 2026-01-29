import { useState, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { 
  FileText, 
  Trash2, 
  Loader2, 
  CheckCircle, 
  AlertCircle,
  Search,
  Library,
  FileUp
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useToast } from "@/hooks/use-toast";
import { EmptyState } from "@/components/EmptyState";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import type { KnowledgeDocument } from "@shared/schema";

export default function KnowledgeBasePage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const { data: documents, isLoading } = useQuery<KnowledgeDocument[]>({
    queryKey: ["/api/knowledge-base"],
    refetchInterval: (query) => {
      // Poll every 2 seconds while any document is processing
      const docs = query.state.data;
      if (docs && docs.some(d => d.status === "processing")) {
        return 2000;
      }
      return false;
    },
  });

  const { data: stats } = useQuery<{ documentCount: number; chunkCount: number }>({
    queryKey: ["/api/knowledge-base/stats"],
    refetchInterval: (query) => {
      // Also refresh stats when documents are processing
      if (documents?.some(d => d.status === "processing")) {
        return 2000;
      }
      return false;
    },
  });

  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append("file", file);
      
      const response = await fetch("/api/knowledge-base/upload", {
        method: "POST",
        body: formData,
      });
      
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || "Upload failed");
      }
      
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/knowledge-base"] });
      queryClient.invalidateQueries({ queryKey: ["/api/knowledge-base/stats"] });
      toast({
        title: "Document uploaded",
        description: "Your document is being processed for the knowledge base.",
      });
    },
    onError: (error: Error) => {
      toast({
        title: "Upload failed",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      const response = await fetch(`/api/knowledge-base/${id}`, {
        method: "DELETE",
      });
      
      if (!response.ok) {
        throw new Error("Delete failed");
      }
      
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/knowledge-base"] });
      queryClient.invalidateQueries({ queryKey: ["/api/knowledge-base/stats"] });
      toast({
        title: "Document deleted",
        description: "The document has been removed from the knowledge base.",
      });
    },
    onError: () => {
      toast({
        title: "Delete failed",
        description: "Could not delete the document.",
        variant: "destructive",
      });
    },
  });

  const handleFileSelect = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setIsUploading(true);
    try {
      await uploadMutation.mutateAsync(file);
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const handleDrop = async (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    const file = event.dataTransfer.files?.[0];
    if (!file) return;

    setIsUploading(true);
    try {
      await uploadMutation.mutateAsync(file);
    } finally {
      setIsUploading(false);
    }
  };

  const handleDragOver = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const filteredDocuments = documents?.filter(doc =>
    doc.originalName.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="flex flex-col h-full">
      <div className="border-b bg-card/50">
        <div className="p-6">
          <div className="flex items-center gap-3 mb-2">
            <div className="flex h-10 w-10 items-center justify-center rounded-md bg-primary">
              <Library className="h-5 w-5 text-primary-foreground" />
            </div>
            <div>
              <h1 className="text-2xl font-bold">Knowledge Base</h1>
              <p className="text-sm text-muted-foreground">
                Upload documents to enhance AI generation with domain knowledge
              </p>
            </div>
          </div>
          {stats && (stats.documentCount > 0 || stats.chunkCount > 0) && (
            <div className="flex gap-4 mt-4">
              <Badge variant="outline" className="text-sm">
                {stats.documentCount} document{stats.documentCount !== 1 ? "s" : ""}
              </Badge>
              <Badge variant="outline" className="text-sm">
                {stats.chunkCount} text chunk{stats.chunkCount !== 1 ? "s" : ""} indexed
              </Badge>
            </div>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-auto p-6">
        <div className="max-w-4xl mx-auto space-y-6">
          <Card
            className="border-2 border-dashed hover:border-primary/50 transition-colors cursor-pointer"
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onClick={() => fileInputRef.current?.click()}
            data-testid="upload-dropzone"
          >
            <CardContent className="flex flex-col items-center justify-center py-10">
              <input
                ref={fileInputRef}
                type="file"
                className="hidden"
                onChange={handleFileSelect}
                accept=".txt,.md,.json,.csv"
                data-testid="input-file-upload"
              />
              {isUploading ? (
                <>
                  <Loader2 className="h-12 w-12 text-primary animate-spin mb-4" />
                  <p className="text-lg font-medium">Uploading...</p>
                </>
              ) : (
                <>
                  <FileUp className="h-12 w-12 text-muted-foreground mb-4" />
                  <p className="text-lg font-medium mb-1">
                    Drop files here or click to upload
                  </p>
                  <p className="text-sm text-muted-foreground">
                    Supports TXT, MD, JSON, CSV files
                  </p>
                </>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between gap-4">
                <CardTitle className="text-lg">Uploaded Documents</CardTitle>
                <div className="relative w-64">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    placeholder="Search documents..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="pl-9"
                    data-testid="input-search-documents"
                  />
                </div>
              </div>
              <CardDescription>
                Documents are processed and indexed for semantic search
              </CardDescription>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <div className="flex items-center justify-center py-10">
                  <LoadingSpinner />
                </div>
              ) : !filteredDocuments?.length ? (
                <EmptyState
                  icon="document"
                  title="No documents yet"
                  description="Upload documents to build your knowledge base for enhanced AI generation."
                />
              ) : (
                <ScrollArea className="h-[400px]">
                  <div className="space-y-3">
                    {filteredDocuments.map((doc) => (
                      <div
                        key={doc.id}
                        className="flex items-center gap-4 p-4 rounded-lg border bg-card hover:bg-muted/50 transition-colors"
                        data-testid={`document-${doc.id}`}
                      >
                        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-muted">
                          <FileText className="h-5 w-5 text-muted-foreground" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="font-medium truncate">{doc.originalName}</p>
                          <div className="flex items-center gap-2 text-xs text-muted-foreground">
                            <span>{formatFileSize(doc.size)}</span>
                            <span>•</span>
                            <span>{formatDate(doc.createdAt)}</span>
                            {doc.status === "ready" && (
                              <>
                                <span>•</span>
                                <span>{doc.chunkCount} chunks</span>
                              </>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          {doc.status === "processing" && (
                            <Badge variant="outline" className="bg-warning/10 text-warning border-warning/30">
                              <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                              Processing
                            </Badge>
                          )}
                          {doc.status === "ready" && (
                            <Badge variant="outline" className="bg-success/10 text-success border-success/30">
                              <CheckCircle className="h-3 w-3 mr-1" />
                              Ready
                            </Badge>
                          )}
                          {doc.status === "error" && (
                            <Badge variant="outline" className="bg-destructive/10 text-destructive border-destructive/30">
                              <AlertCircle className="h-3 w-3 mr-1" />
                              Error
                            </Badge>
                          )}
                          <Button
                            size="icon"
                            variant="ghost"
                            onClick={(e) => {
                              e.stopPropagation();
                              deleteMutation.mutate(doc.id);
                            }}
                            disabled={deleteMutation.isPending}
                            data-testid={`button-delete-${doc.id}`}
                          >
                            <Trash2 className="h-4 w-4 text-muted-foreground hover:text-destructive" />
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              )}
            </CardContent>
          </Card>

          <Card className="bg-muted/30">
            <CardContent className="pt-6">
              <div className="flex items-start gap-4">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-primary/10">
                  <Search className="h-5 w-5 text-primary" />
                </div>
                <div>
                  <h3 className="font-medium mb-1">How it works</h3>
                  <p className="text-sm text-muted-foreground">
                    Documents are split into chunks and stored in MongoDB Atlas. 
                    When you generate BRDs or user stories, the system automatically 
                    searches for relevant information using keyword matching to 
                    provide better context for AI generation.
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
