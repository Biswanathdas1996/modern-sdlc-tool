import { useState, useRef } from "react";
import { useLocation } from "wouter";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FileText, Upload, Mic, MicOff, FileUp, X, ArrowRight, Check, AlertCircle, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Label } from "@/components/ui/label";
import { WorkflowHeader } from "@/components/WorkflowHeader";
import { LoadingOverlay } from "@/components/LoadingSpinner";
import { apiRequest } from "@/lib/queryClient";
import { cn } from "@/lib/utils";

const workflowSteps = [
  { id: "analyze", label: "Analyze", completed: true, active: false },
  { id: "document", label: "Document", completed: true, active: false },
  { id: "requirements", label: "Requirements", completed: false, active: true },
  { id: "brd", label: "BRD", completed: false, active: false },
  { id: "test-cases", label: "Tests", completed: false, active: false },
];

export default function RequirementsPage() {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [inputType, setInputType] = useState<"text" | "file" | "audio">("text");
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [, navigate] = useLocation();
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const [isGeneratingBRD, setIsGeneratingBRD] = useState(false);
  const [generationStatus, setGenerationStatus] = useState("");

  const submitMutation = useMutation({
    mutationFn: async (data: FormData) => {
      // Step 1: Submit requirements
      setGenerationStatus("Submitting requirements...");
      const response = await fetch("/api/requirements", {
        method: "POST",
        body: data,
      });
      if (!response.ok) throw new Error("Failed to submit requirements");
      const requirements = await response.json();

      // Step 2: Generate BRD (with streaming)
      setIsGeneratingBRD(true);
      setGenerationStatus("Generating BRD...");
      
      const brdResponse = await fetch("/api/brd/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      
      if (!brdResponse.ok) throw new Error("Failed to generate BRD");

      // Read the streaming response to completion
      const reader = brdResponse.body?.getReader();
      if (!reader) throw new Error("No response body");

      const decoder = new TextDecoder();
      let brdComplete = false;

      while (!brdComplete) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split("\n");

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.done) {
                brdComplete = true;
              }
            } catch (e) {
              // Ignore parse errors
            }
          }
        }
      }

      return requirements;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/requirements"] });
      queryClient.invalidateQueries({ queryKey: ["/api/brd/current"] });
      setIsGeneratingBRD(false);
      setGenerationStatus("");
      navigate("/brd");
    },
    onError: () => {
      setIsGeneratingBRD(false);
      setGenerationStatus("");
    },
  });

  const handleFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      setUploadedFile(file);
      setInputType("file");
    }
  };

  const removeFile = () => {
    setUploadedFile(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream, { mimeType: "audio/webm;codecs=opus" });
      mediaRecorderRef.current = mediaRecorder;
      chunksRef.current = [];

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      mediaRecorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        setAudioBlob(blob);
        stream.getTracks().forEach((t) => t.stop());
      };

      mediaRecorder.start(100);
      setIsRecording(true);
      setInputType("audio");
    } catch (error) {
      console.error("Failed to start recording:", error);
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === "recording") {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  const removeAudio = () => {
    setAudioBlob(null);
  };

  const handleSubmit = () => {
    const formData = new FormData();
    formData.append("title", title);
    formData.append("description", description);
    formData.append("inputType", inputType);

    if (uploadedFile) {
      formData.append("file", uploadedFile);
    }
    if (audioBlob) {
      formData.append("audio", audioBlob, "recording.webm");
    }

    submitMutation.mutate(formData);
  };

  const isValid = title.trim() && (description.trim() || uploadedFile || audioBlob);

  return (
    <div className="flex flex-col h-full">
      {submitMutation.isPending && (
        <LoadingOverlay
          message="Processing Requirements..."
          subMessage="Analyzing your input and preparing for BRD generation"
        />
      )}

      <WorkflowHeader
        steps={workflowSteps}
        title="Feature Requirements"
        description="Describe your new feature requirements. You can type, upload a document, or use voice input."
      />

      <div className="flex-1 overflow-auto p-6">
        <div className="max-w-3xl mx-auto space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Feature Title</CardTitle>
              <CardDescription>Give your feature request a clear, descriptive title</CardDescription>
            </CardHeader>
            <CardContent>
              <Input
                placeholder="e.g., User Dashboard with Analytics"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                data-testid="input-feature-title"
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Requirements Input</CardTitle>
              <CardDescription>Choose how you want to provide your feature requirements</CardDescription>
            </CardHeader>
            <CardContent>
              <Tabs value={inputType} onValueChange={(v) => setInputType(v as typeof inputType)}>
                <TabsList className="grid w-full grid-cols-3 mb-6">
                  <TabsTrigger value="text" className="flex items-center gap-2" data-testid="tab-text">
                    <FileText className="h-4 w-4" />
                    Text
                  </TabsTrigger>
                  <TabsTrigger value="file" className="flex items-center gap-2" data-testid="tab-file">
                    <Upload className="h-4 w-4" />
                    File
                  </TabsTrigger>
                  <TabsTrigger value="audio" className="flex items-center gap-2" data-testid="tab-audio">
                    <Mic className="h-4 w-4" />
                    Voice
                  </TabsTrigger>
                </TabsList>

                <TabsContent value="text" className="space-y-4">
                  <div>
                    <Label htmlFor="description">Description</Label>
                    <Textarea
                      id="description"
                      placeholder="Describe your feature requirements in detail. Include user stories, acceptance criteria, and any specific technical requirements..."
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      className="min-h-[200px] mt-2"
                      data-testid="textarea-description"
                    />
                  </div>
                  <div className="text-sm text-muted-foreground">
                    <p className="font-medium mb-2">Tips for better results:</p>
                    <ul className="list-disc pl-5 space-y-1">
                      <li>Be specific about user interactions and flows</li>
                      <li>Include acceptance criteria when possible</li>
                      <li>Mention any technical constraints or preferences</li>
                      <li>Describe expected inputs and outputs</li>
                    </ul>
                  </div>
                </TabsContent>

                <TabsContent value="file" className="space-y-4">
                  <div
                    className={cn(
                      "border-2 border-dashed rounded-lg p-8 text-center transition-colors",
                      uploadedFile
                        ? "border-success bg-success/5"
                        : "border-border hover:border-primary/50 hover:bg-muted/50"
                    )}
                    onClick={() => !uploadedFile && fileInputRef.current?.click()}
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={(e) => {
                      e.preventDefault();
                      const file = e.dataTransfer.files[0];
                      if (file) {
                        setUploadedFile(file);
                        setInputType("file");
                      }
                    }}
                  >
                    <input
                      type="file"
                      ref={fileInputRef}
                      onChange={handleFileUpload}
                      accept=".txt,.doc,.docx,.pdf,.md"
                      className="hidden"
                      data-testid="input-file"
                    />

                    {uploadedFile ? (
                      <div className="flex items-center justify-center gap-3">
                        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-success/10">
                          <Check className="h-6 w-6 text-success" />
                        </div>
                        <div className="text-left">
                          <p className="font-medium text-foreground">{uploadedFile.name}</p>
                          <p className="text-sm text-muted-foreground">
                            {(uploadedFile.size / 1024).toFixed(1)} KB
                          </p>
                        </div>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={(e) => {
                            e.stopPropagation();
                            removeFile();
                          }}
                          data-testid="button-remove-file"
                        >
                          <X className="h-4 w-4" />
                        </Button>
                      </div>
                    ) : (
                      <div className="space-y-3">
                        <div className="flex h-12 w-12 mx-auto items-center justify-center rounded-full bg-muted">
                          <FileUp className="h-6 w-6 text-muted-foreground" />
                        </div>
                        <div>
                          <p className="font-medium text-foreground">Drop your file here or click to browse</p>
                          <p className="text-sm text-muted-foreground mt-1">
                            Supports .txt, .doc, .docx, .pdf, .md files
                          </p>
                        </div>
                      </div>
                    )}
                  </div>
                </TabsContent>

                <TabsContent value="audio" className="space-y-4">
                  <div className="flex flex-col items-center justify-center p-8 border-2 border-dashed rounded-lg border-border">
                    {audioBlob ? (
                      <div className="flex flex-col items-center gap-4">
                        <div className="flex h-16 w-16 items-center justify-center rounded-full bg-success/10">
                          <Check className="h-8 w-8 text-success" />
                        </div>
                        <p className="font-medium text-foreground">Recording saved</p>
                        <audio controls src={URL.createObjectURL(audioBlob)} className="w-full max-w-md" />
                        <Button variant="outline" onClick={removeAudio} data-testid="button-remove-audio">
                          <X className="h-4 w-4 mr-2" />
                          Remove Recording
                        </Button>
                      </div>
                    ) : (
                      <div className="flex flex-col items-center gap-4">
                        <Button
                          size="lg"
                          variant={isRecording ? "destructive" : "default"}
                          className={cn(
                            "h-20 w-20 rounded-full",
                            isRecording && "animate-pulse"
                          )}
                          onClick={isRecording ? stopRecording : startRecording}
                          data-testid="button-record"
                        >
                          {isRecording ? (
                            <MicOff className="h-8 w-8" />
                          ) : (
                            <Mic className="h-8 w-8" />
                          )}
                        </Button>
                        <p className="text-center">
                          {isRecording ? (
                            <span className="text-destructive font-medium">Recording... Click to stop</span>
                          ) : (
                            <span className="text-muted-foreground">Click to start recording</span>
                          )}
                        </p>
                        <p className="text-sm text-muted-foreground text-center max-w-md">
                          Speak clearly about your feature requirements. The AI will transcribe and analyze your input.
                        </p>
                      </div>
                    )}
                  </div>
                </TabsContent>
              </Tabs>
            </CardContent>
          </Card>

          {submitMutation.isError && (
            <Card className="border-destructive bg-destructive/5">
              <CardContent className="pt-6">
                <div className="flex items-center gap-2 text-destructive">
                  <AlertCircle className="h-5 w-5" />
                  <p>Failed to submit requirements. Please try again.</p>
                </div>
              </CardContent>
            </Card>
          )}

          <div className="flex justify-end gap-3">
            <Button variant="outline" onClick={() => navigate("/documentation")} disabled={submitMutation.isPending}>
              Back
            </Button>
            <Button
              onClick={handleSubmit}
              disabled={!isValid || submitMutation.isPending}
              data-testid="button-submit-requirements"
            >
              {submitMutation.isPending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  {generationStatus || "Processing..."}
                </>
              ) : (
                <>
                  Generate BRD
                  <ArrowRight className="ml-2 h-4 w-4" />
                </>
              )}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
