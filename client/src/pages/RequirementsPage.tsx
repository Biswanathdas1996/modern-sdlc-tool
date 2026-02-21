import { useState, useRef } from "react";
import { useLocation } from "wouter";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FileText, Upload, Mic, MicOff, FileUp, X, ArrowRight, Check, AlertCircle, Loader2, Lightbulb, Bug, RefreshCw } from "lucide-react";
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
import { useSession } from "@/hooks/useSession";
import { useProject } from "@/hooks/useProject";

const workflowSteps = [
  { id: "analyze", label: "Analyze", completed: true, active: false },
  { id: "document", label: "Document", completed: true, active: false },
  { id: "requirements", label: "Requirements", completed: false, active: true },
  { id: "brd", label: "BRD", completed: false, active: false },
  { id: "user-stories", label: "Stories", completed: false, active: false },
  { id: "test-cases", label: "Tests", completed: false, active: false },
  { id: "test-data", label: "Data", completed: false, active: false },
];

type RequestType = "feature" | "bug" | "change_request";

const requestTypeLabels: Record<RequestType, { title: string; description: string; placeholder: string; jiraType: string }> = {
  feature: {
    title: "New Feature",
    description: "Describe a new feature or enhancement you want to add to the system.",
    placeholder: "Describe the new feature in detail. Include user stories, acceptance criteria, and expected behavior...",
    jiraType: "Story"
  },
  bug: {
    title: "Bug Report", 
    description: "Report an issue or defect that needs to be fixed.",
    placeholder: "Describe the bug in detail. Include steps to reproduce, expected vs actual behavior, and any error messages...",
    jiraType: "Bug"
  },
  change_request: {
    title: "Change Request",
    description: "Request a modification to existing functionality.",
    placeholder: "Describe the change you need. Include the current behavior, desired behavior, and reason for the change...",
    jiraType: "Task"
  }
};

export default function RequirementsPage() {
  const [requestType, setRequestType] = useState<RequestType>("feature");
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
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);


  const { startSession, saveSessionArtifact, getSessionArtifact } = useSession();
  const { currentProjectId } = useProject();

  const submitMutation = useMutation({
    mutationFn: async (data: FormData) => {
      const response = await fetch("/api/requirements", {
        method: "POST",
        body: data,
      });
      if (!response.ok) throw new Error("Failed to submit requirements");
      const requirements = await response.json();
      saveSessionArtifact("featureRequest", requirements);

      return requirements;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/requirements"] });
      queryClient.invalidateQueries({ queryKey: ["/api/brd/current", currentProjectId] });
      navigate("/brd?auto_generate=true");
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
    const sessionId = startSession({ featureTitle: title, requestType });
    setCurrentSessionId(sessionId);
    saveSessionArtifact("featureRequest", { title, description, inputType, requestType });

    const formData = new FormData();
    formData.append("title", title);
    formData.append("description", description);
    formData.append("inputType", inputType);
    formData.append("requestType", requestType);
    formData.append("sessionId", sessionId);

    if (currentProjectId) {
      formData.append("project_id", currentProjectId);
    }
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
          message="Submitting Requirements..."
          subMessage="Saving your input and redirecting to BRD generation"
        />
      )}

      <WorkflowHeader
        steps={workflowSteps}
        title="Requirements Input"
        description="Select the type of request and provide details. Creates the appropriate issue in JIRA."
      />

      <div className="flex-1 overflow-auto p-6">
        <div className="max-w-3xl mx-auto space-y-6">
          {/* Request Type Tabs */}
          <Tabs value={requestType} onValueChange={(v) => setRequestType(v as RequestType)}>
            <TabsList className="grid w-full grid-cols-3">
              <TabsTrigger value="feature" className="flex items-center gap-2" data-testid="tab-feature">
                <Lightbulb className="h-4 w-4" />
                New Feature
              </TabsTrigger>
              <TabsTrigger value="bug" className="flex items-center gap-2" data-testid="tab-bug">
                <Bug className="h-4 w-4" />
                Bug Report
              </TabsTrigger>
              <TabsTrigger value="change_request" className="flex items-center gap-2" data-testid="tab-change-request">
                <RefreshCw className="h-4 w-4" />
                Change Request
              </TabsTrigger>
            </TabsList>

            <div className="mt-4 p-4 bg-muted/50 rounded-lg">
              <div className="flex items-center gap-2 text-sm">
                <Badge variant="secondary">{requestTypeLabels[requestType].jiraType}</Badge>
                <span className="text-muted-foreground">{requestTypeLabels[requestType].description}</span>
              </div>
            </div>
          </Tabs>

          <Card>
            <CardHeader>
              <CardTitle>{requestTypeLabels[requestType].title} Title</CardTitle>
              <CardDescription>Give your {requestType === "bug" ? "bug report" : requestType === "change_request" ? "change request" : "feature"} a clear, descriptive title</CardDescription>
            </CardHeader>
            <CardContent>
              <Input
                placeholder={requestType === "bug" ? "e.g., Login fails with incorrect error message" : requestType === "change_request" ? "e.g., Update password validation rules" : "e.g., User Dashboard with Analytics"}
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                data-testid="input-feature-title"
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Request Details</CardTitle>
              <CardDescription>Choose how you want to provide your {requestType === "bug" ? "bug details" : "requirements"}</CardDescription>
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
                      placeholder={requestTypeLabels[requestType].placeholder}
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      className="min-h-[200px] mt-2"
                      data-testid="textarea-description"
                    />
                  </div>
                  <div className="text-sm text-muted-foreground">
                    <p className="font-medium mb-2">Tips for better results:</p>
                    <ul className="list-disc pl-5 space-y-1">
                      {requestType === "bug" ? (
                        <>
                          <li>Include steps to reproduce the bug</li>
                          <li>Describe expected vs actual behavior</li>
                          <li>Include any error messages or logs</li>
                          <li>Mention browser/device if relevant</li>
                        </>
                      ) : requestType === "change_request" ? (
                        <>
                          <li>Describe the current behavior clearly</li>
                          <li>Explain what needs to change and why</li>
                          <li>Include any business justification</li>
                          <li>Note any dependencies or impacts</li>
                        </>
                      ) : (
                        <>
                          <li>Be specific about user interactions and flows</li>
                          <li>Include acceptance criteria when possible</li>
                          <li>Mention any technical constraints or preferences</li>
                          <li>Describe expected inputs and outputs</li>
                        </>
                      )}
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
                          Speak clearly about your {requestType === "bug" ? "bug report" : requestType === "change_request" ? "change request" : "feature requirements"}. The AI will transcribe and analyze your input.
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
                  Submitting...
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
