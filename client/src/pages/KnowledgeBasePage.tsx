import { useState, useRef, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { 
  FileText, 
  Trash2, 
  Loader2, 
  CheckCircle, 
  AlertCircle,
  Search,
  Library,
  FileUp,
  Database,
  Cpu,
  FileSearch
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useToast } from "@/hooks/use-toast";
import { useProject } from "@/hooks/useProject";
import { EmptyState } from "@/components/EmptyState";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import type { KnowledgeDocument } from "@shared/schema";

interface UploadProgress {
  step: string;
  detail: string;
}

const STEP_ICONS: Record<string, typeof Loader2> = {
  upload: FileUp,
  document_created: Database,
  preparing: Database,
  chunking: FileSearch,
  chunking_done: FileSearch,
  embedding: Cpu,
  embedding_done: Cpu,
  storing: Database,
  storing_done: Database,
  indexing: Search,
  indexing_done: Search,
  complete: CheckCircle,
  done: CheckCircle,
  error: AlertCircle,
};

const STEP_LABELS: Record<string, string> = {
  upload: "Uploading",
  document_created: "Document Created",
  preparing: "Preparing Collection",
  chunking: "Chunking Document",
  chunking_done: "Chunking Complete",
  embedding: "Generating Embeddings",
  embedding_done: "Embeddings Generated",
  storing: "Storing Chunks",
  storing_done: "Chunks Stored",
  indexing: "Creating Vector Index",
  indexing_done: "Index Ready",
  complete: "Complete",
  done: "Complete",
  error: "Error",
};

export default function KnowledgeBasePage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [uploadSteps, setUploadSteps] = useState<UploadProgress[]>([]);
  const [currentStep, setCurrentStep] = useState<UploadProgress | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const { currentProjectId } = useProject();

  const kbQueryParam = currentProjectId ? `?project_id=${currentProjectId}` : "";

  const { data: documents, isLoading } = useQuery<KnowledgeDocument[]>({
    queryKey: ["/api/knowledge-base", currentProjectId],
    queryFn: async () => {
      const res = await fetch(`/api/knowledge-base${kbQueryParam}`);
      if (!res.ok) throw new Error("Failed to fetch documents");
      return res.json();
    },
    refetchInterval: (query) => {
      const docs = query.state.data;
      if (docs && docs.some(d => d.status === "processing")) {
        return 2000;
      }
      return false;
    },
  });

  const { data: stats } = useQuery<{ documentCount: number; chunkCount: number }>({
    queryKey: ["/api/knowledge-base/stats", currentProjectId],
    queryFn: async () => {
      const res = await fetch(`/api/knowledge-base/stats${kbQueryParam}`);
      if (!res.ok) throw new Error("Failed to fetch stats");
      return res.json();
    },
    refetchInterval: (query) => {
      if (documents?.some(d => d.status === "processing")) {
        return 2000;
      }
      return false;
    },
  });

  const uploadWithProgress = useCallback(async (file: File) => {
    setIsUploading(true);
    setUploadSteps([]);
    setCurrentStep(null);
    
    try {
      const formData = new FormData();
      formData.append("file", file);
      if (currentProjectId) {
        formData.append("project_id", currentProjectId);
      }
      
      const response = await fetch("/api/knowledge-base/upload", {
        method: "POST",
        body: formData,
      });
      
      if (!response.ok) {
        let errorMsg = "Upload failed";
        try {
          const errData = await response.json();
          errorMsg = errData.detail || errData.error || errorMsg;
        } catch {}
        throw new Error(errorMsg);
      }
      
      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      
      if (!reader) {
        throw new Error("No response stream available");
      }
      
      let buffer = "";
      
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const data = JSON.parse(line.slice(6));
              const progress: UploadProgress = {
                step: data.step,
                detail: data.detail,
              };
              
              setCurrentStep(progress);
              setUploadSteps(prev => [...prev, progress]);
              
              if (data.step === "done") {
                queryClient.invalidateQueries({ queryKey: ["/api/knowledge-base"] });
                queryClient.invalidateQueries({ queryKey: ["/api/knowledge-base/stats"] });
                toast({
                  title: "Document uploaded & indexed",
                  description: data.detail,
                });
              }
              
              if (data.step === "error") {
                toast({
                  title: "Upload error",
                  description: data.detail,
                  variant: "destructive",
                });
              }
            } catch {}
          }
        }
      }
      
      setTimeout(() => {
        setIsUploading(false);
        setUploadSteps([]);
        setCurrentStep(null);
      }, 2000);
      
    } catch (error: any) {
      toast({
        title: "Upload failed",
        description: error.message || "Something went wrong",
        variant: "destructive",
      });
      setIsUploading(false);
      setUploadSteps([]);
      setCurrentStep(null);
    } finally {
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  }, [currentProjectId, queryClient, toast]);

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      const response = await fetch(`/api/knowledge-base/${id}?project_id=${currentProjectId}`, {
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
    await uploadWithProgress(file);
  };

  const handleDrop = async (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    const file = event.dataTransfer.files?.[0];
    if (!file) return;
    await uploadWithProgress(file);
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
            className={`border-2 border-dashed transition-colors ${isUploading ? "border-primary/50 bg-primary/5" : "hover:border-primary/50 cursor-pointer"}`}
            onDrop={isUploading ? undefined : handleDrop}
            onDragOver={isUploading ? undefined : handleDragOver}
            onClick={isUploading ? undefined : () => fileInputRef.current?.click()}
            data-testid="upload-dropzone"
          >
            <CardContent className="flex flex-col items-center justify-center py-10">
              <input
                ref={fileInputRef}
                type="file"
                className="hidden"
                onChange={handleFileSelect}
                accept=".txt,.md,.json,.csv,.pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                data-testid="input-file-upload"
              />
              {isUploading ? (
                <div className="w-full max-w-md" data-testid="upload-progress">
                  <div className="flex items-center gap-3 mb-4">
                    <Loader2 className="h-6 w-6 text-primary animate-spin shrink-0" />
                    <p className="text-lg font-medium">
                      {currentStep ? (STEP_LABELS[currentStep.step] || currentStep.step) : "Processing..."}
                    </p>
                  </div>
                  
                  {currentStep && (
                    <p className="text-sm text-muted-foreground mb-4" data-testid="text-current-step">
                      {currentStep.detail}
                    </p>
                  )}
                  
                  <div className="space-y-2">
                    {uploadSteps.map((step, idx) => {
                      const StepIcon = STEP_ICONS[step.step] || Loader2;
                      const isComplete = step.step.endsWith("_done") || step.step === "done" || step.step === "complete";
                      const isError = step.step === "error";
                      const isActive = idx === uploadSteps.length - 1 && !isComplete && !isError;
                      
                      return (
                        <div 
                          key={idx} 
                          className={`flex items-start gap-2 text-xs rounded-md px-3 py-1.5 ${
                            isError ? "text-destructive bg-destructive/10" : 
                            isComplete ? "text-green-600 dark:text-green-400 bg-green-500/10" : 
                            isActive ? "text-primary bg-primary/10" : 
                            "text-muted-foreground"
                          }`}
                          data-testid={`step-${step.step}`}
                        >
                          {isActive ? (
                            <Loader2 className="h-3.5 w-3.5 mt-0.5 shrink-0 animate-spin" />
                          ) : (
                            <StepIcon className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                          )}
                          <span>{step.detail}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ) : (
                <>
                  <FileUp className="h-12 w-12 text-muted-foreground mb-4" />
                  <p className="text-lg font-medium mb-1">
                    Drop files here or click to upload
                  </p>
                  <p className="text-sm text-muted-foreground">
                    Supports PDF, Word, TXT, MD, JSON, CSV files
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
                    Documents are split into semantic chunks, embedded using BAAI/bge-small-en-v1.5 (384-dim vectors), 
                    and indexed with Atlas Vector Search for each project. When you generate BRDs or user stories, the 
                    system performs semantic similarity search to find the most relevant content for AI generation.
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
