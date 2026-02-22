import { useState, useRef, useCallback, useEffect } from "react";
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
  FileSearch,
  Image,
  Eye,
  MessageSquare,
  Send,
  Bot,
  User,
  ChevronDown,
  ChevronUp,
  FileIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/hooks/use-toast";
import { useProject } from "@/hooks/useProject";
import { EmptyState } from "@/components/EmptyState";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import type { KnowledgeDocument } from "@shared/schema";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  sources?: { filename: string; score: number; preview: string }[];
}

interface ChatSource {
  filename: string;
  score: number;
  preview: string;
}

interface UploadProgress {
  step: string;
  detail: string;
}

const STEP_ICONS: Record<string, typeof Loader2> = {
  upload: FileUp,
  parsing: FileSearch,
  parsing_done: FileSearch,
  captioning: Eye,
  captioning_progress: Eye,
  captioning_done: Eye,
  captioning_warning: AlertCircle,
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
  parsing: "Parsing Document",
  parsing_done: "Document Parsed",
  captioning: "Captioning Images",
  captioning_progress: "Captioning Images",
  captioning_done: "Images Captioned",
  captioning_warning: "Captioning Warning",
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

  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [isChatLoading, setIsChatLoading] = useState(false);
  const [chatOpen, setChatOpen] = useState(true);
  const [expandedSources, setExpandedSources] = useState<number | null>(null);
  const chatScrollRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const readyDocs = documents?.filter(d => d.status === "ready") ?? [];
  const chatEnabled = readyDocs.length > 0;

  useEffect(() => {
    if (chatScrollRef.current) {
      chatScrollRef.current.scrollTop = chatScrollRef.current.scrollHeight;
    }
  }, [chatMessages, isChatLoading]);

  useEffect(() => {
    return () => { abortControllerRef.current?.abort(); };
  }, []);

  const parseSSELine = (line: string, state: { assistantContent: string; sources: ChatSource[] }) => {
    const trimmed = line.replace(/\r$/, "");
    if (!trimmed.startsWith("data: ")) return;
    try {
      const data = JSON.parse(trimmed.slice(6));
      if (data.type === "sources") {
        state.sources = data.sources || [];
      } else if (data.type === "chunk" || data.type === "error") {
        state.assistantContent += data.content;
        const content = state.assistantContent;
        const sources = state.sources;
        setChatMessages(prev => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last?.role === "assistant") {
            updated[updated.length - 1] = { ...last, content, sources };
          } else {
            updated.push({ role: "assistant", content, sources });
          }
          return updated;
        });
      }
    } catch {}
  };

  const sendChatMessage = useCallback(async () => {
    const question = chatInput.trim();
    if (!question || !currentProjectId || isChatLoading || !chatEnabled) return;

    abortControllerRef.current?.abort();
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setChatInput("");
    setChatMessages(prev => [...prev, { role: "user", content: question }]);
    setIsChatLoading(true);

    try {
      const response = await fetch("/api/knowledge-base/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, project_id: currentProjectId }),
        signal: controller.signal,
      });

      if (!response.ok) {
        let msg = "Chat request failed";
        try { const d = await response.json(); msg = d.detail || msg; } catch {}
        throw new Error(msg);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error("No response stream");

      const decoder = new TextDecoder();
      let buffer = "";
      const state = { assistantContent: "", sources: [] as ChatSource[] };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) parseSSELine(line, state);
      }

      if (buffer.trim()) parseSSELine(buffer, state);

      if (!state.assistantContent) {
        setChatMessages(prev => [...prev, { role: "assistant", content: "No response received.", sources: state.sources }]);
      }
    } catch (error: any) {
      if (error.name === "AbortError") return;
      setChatMessages(prev => [...prev, { role: "assistant", content: `Error: ${error.message}` }]);
    } finally {
      setIsChatLoading(false);
    }
  }, [chatInput, currentProjectId, isChatLoading, chatEnabled]);

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
      
      await new Promise(resolve => setTimeout(resolve, 3000));
      setIsUploading(false);
      setUploadSteps([]);
      setCurrentStep(null);
      
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
                accept=".txt,.md,.json,.csv,.pdf,.docx,.pptx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.openxmlformats-officedocument.presentationml.presentation"
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
                      const isWarning = step.step.endsWith("_warning");
                      const isActive = idx === uploadSteps.length - 1 && !isComplete && !isError;
                      
                      return (
                        <div 
                          key={idx} 
                          className={`flex items-start gap-2 text-xs rounded-md px-3 py-1.5 ${
                            isError ? "text-destructive bg-destructive/10" : 
                            isWarning ? "text-yellow-600 dark:text-yellow-400 bg-yellow-500/10" :
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
                  <p className="text-sm text-muted-foreground" data-testid="text-supported-formats">
                    Supports PDF, Word, PowerPoint, TXT, MD, JSON, CSV files
                  </p>
                  <p className="text-xs text-muted-foreground mt-1" data-testid="text-image-processing-hint">
                    Images in documents are automatically extracted and captioned by AI
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
                            {doc.imageCount && doc.imageCount > 0 && (
                              <>
                                <span>•</span>
                                <span className="flex items-center gap-0.5" data-testid={`text-image-count-${doc.id}`}>
                                  <Image className="h-3 w-3" />
                                  {doc.captionedImageCount || doc.imageCount} images
                                </span>
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

          <Card data-testid="card-rag-chat">
            <CardHeader className="pb-3">
              <button
                type="button"
                className="flex items-center justify-between w-full text-left"
                onClick={() => setChatOpen(prev => !prev)}
                data-testid="button-toggle-chat"
              >
                <div className="flex items-center gap-2">
                  <MessageSquare className="h-5 w-5 text-primary" />
                  <CardTitle className="text-lg">Test RAG Chat</CardTitle>
                </div>
                <div className="flex items-center gap-2">
                  {chatMessages.length > 0 && (
                    <Badge variant="outline" className="text-xs" data-testid="badge-chat-count">
                      {chatMessages.filter(m => m.role === "user").length} question{chatMessages.filter(m => m.role === "user").length !== 1 ? "s" : ""}
                    </Badge>
                  )}
                  {chatOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                </div>
              </button>
              <CardDescription>
                Ask questions about your uploaded documents to test the RAG pipeline
              </CardDescription>
            </CardHeader>
            {chatOpen && (
              <CardContent className="pt-0">
                <div
                  ref={chatScrollRef}
                  className="h-[350px] overflow-y-auto border rounded-lg bg-background mb-3 p-3 space-y-4"
                  data-testid="chat-messages"
                >
                  {chatMessages.length === 0 && !isChatLoading && (
                    <div className="flex flex-col items-center justify-center h-full text-muted-foreground" data-testid="chat-empty-state">
                      <Bot className="h-10 w-10 mb-3 opacity-40" />
                      <p className="text-sm font-medium">Ask a question about your documents</p>
                      <p className="text-xs mt-1 opacity-70">The system will search the knowledge base and generate an answer</p>
                    </div>
                  )}

                  {chatMessages.map((msg, idx) => (
                    <div key={idx} className={`flex gap-3 ${msg.role === "user" ? "justify-end" : "justify-start"}`} data-testid={`chat-message-${idx}`}>
                      {msg.role === "assistant" && (
                        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10">
                          <Bot className="h-4 w-4 text-primary" />
                        </div>
                      )}
                      <div className={`max-w-[80%] space-y-2 ${msg.role === "user" ? "order-first" : ""}`}>
                        <div
                          className={`rounded-lg px-3 py-2 text-sm whitespace-pre-wrap ${
                            msg.role === "user"
                              ? "bg-primary text-primary-foreground ml-auto"
                              : "bg-muted"
                          }`}
                          data-testid={`chat-content-${idx}`}
                        >
                          {msg.content}
                        </div>

                        {msg.role === "assistant" && msg.sources && msg.sources.length > 0 && (
                          <div className="ml-0">
                            <Button
                              variant="ghost"
                              size="sm"
                              className="flex items-center gap-1 text-xs text-muted-foreground h-auto px-1 py-0.5"
                              onClick={() => setExpandedSources(expandedSources === idx ? null : idx)}
                              data-testid={`button-sources-${idx}`}
                            >
                              <FileIcon className="h-3 w-3" />
                              {msg.sources.length} source{msg.sources.length !== 1 ? "s" : ""} used
                              {expandedSources === idx ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                            </Button>
                            {expandedSources === idx && (
                              <div className="mt-1 space-y-1" data-testid={`sources-list-${idx}`}>
                                {msg.sources.map((src, si) => (
                                  <div key={si} className="text-xs border rounded p-2 bg-muted/50" data-testid={`source-item-${idx}-${si}`}>
                                    <div className="flex items-center gap-2 mb-1">
                                      <FileText className="h-3 w-3 shrink-0 text-muted-foreground" />
                                      <span className="font-medium truncate">{src.filename}</span>
                                      <Badge variant="outline" className="text-[10px] px-1 py-0 shrink-0">
                                        {(src.score * 100).toFixed(0)}%
                                      </Badge>
                                    </div>
                                    <p className="text-muted-foreground line-clamp-2">{src.preview}</p>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                      {msg.role === "user" && (
                        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-muted">
                          <User className="h-4 w-4" />
                        </div>
                      )}
                    </div>
                  ))}

                  {isChatLoading && chatMessages[chatMessages.length - 1]?.role !== "assistant" && (
                    <div className="flex gap-3" data-testid="chat-loading">
                      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10">
                        <Bot className="h-4 w-4 text-primary" />
                      </div>
                      <div className="bg-muted rounded-lg px-3 py-2 text-sm">
                        <Loader2 className="h-4 w-4 animate-spin" />
                      </div>
                    </div>
                  )}
                </div>

                <div className="flex gap-2">
                  <Textarea
                    placeholder="Ask a question about your documents..."
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        sendChatMessage();
                      }
                    }}
                    className="min-h-[44px] max-h-[120px] resize-none"
                    disabled={isChatLoading || !chatEnabled}
                    data-testid="input-chat"
                  />
                  <Button
                    onClick={sendChatMessage}
                    disabled={isChatLoading || !chatInput.trim() || !chatEnabled}
                    size="icon"
                    data-testid="button-send-chat"
                  >
                    {isChatLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                  </Button>
                </div>
                {!chatEnabled && (
                  <p className="text-xs text-muted-foreground mt-2" data-testid="text-chat-no-docs">
                    {documents?.length ? "Documents are still processing — chat will be available once indexing is complete" : "Upload documents first to start chatting with the knowledge base"}
                  </p>
                )}
              </CardContent>
            )}
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
