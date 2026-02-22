import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Loader2,
  Search,
  FileText,
  Pencil,
  ChevronDown,
  ChevronUp,
  Tag,
  History,
  Copy,
  Check,
  Bot,
  User,
  Code,
  Hash,
  Filter,
  Layers,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useToast } from "@/hooks/use-toast";
import { apiRequest, queryClient } from "@/lib/queryClient";

interface Prompt {
  id: string;
  promptKey: string;
  category: string;
  content: string;
  description: string | null;
  promptType: string;
  isActive: boolean;
  version: number;
  createdAt: string | null;
  updatedAt: string | null;
}

const TYPE_CONFIG: Record<string, { icon: typeof Bot; label: string; color: string }> = {
  system: { icon: Bot, label: "System", color: "text-blue-500 bg-blue-500/10 border-blue-500/20" },
  user: { icon: User, label: "User", color: "text-emerald-500 bg-emerald-500/10 border-emerald-500/20" },
  template: { icon: Code, label: "Template", color: "text-amber-500 bg-amber-500/10 border-amber-500/20" },
};

export default function PromptManagementTab() {
  const { toast } = useToast();
  const [selectedCategory, setSelectedCategory] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [expandedPrompt, setExpandedPrompt] = useState<string | null>(null);
  const [editingPrompt, setEditingPrompt] = useState<Prompt | null>(null);
  const [editContent, setEditContent] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editType, setEditType] = useState("system");
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const { data: promptsData, isLoading } = useQuery<{
    success: boolean;
    data: { prompts: Prompt[]; total: number; categories: string[] };
  }>({
    queryKey: ["/api/prompts", selectedCategory, searchQuery],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (selectedCategory !== "all") params.set("category", selectedCategory);
      if (searchQuery) params.set("search", searchQuery);
      params.set("limit", "500");
      const res = await fetch(`/api/prompts?${params.toString()}`, {
        credentials: "include",
      });
      return res.json();
    },
  });

  const { data: categoriesData } = useQuery<{
    success: boolean;
    data: { name: string; count: number; activeCount: number }[];
  }>({
    queryKey: ["/api/prompts-categories"],
    queryFn: async () => {
      const res = await fetch("/api/prompts-categories", {
        credentials: "include",
      });
      return res.json();
    },
  });

  const updateMutation = useMutation({
    mutationFn: async (payload: {
      id: string;
      content?: string;
      description?: string;
      promptType?: string;
    }) => {
      const res = await apiRequest("PUT", `/api/prompts/${payload.id}`, payload);
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/prompts"] });
      queryClient.invalidateQueries({ queryKey: ["/api/prompts-categories"] });
      setEditingPrompt(null);
      toast({ title: "Prompt updated", description: "Changes saved successfully" });
    },
    onError: (err: any) => {
      toast({ title: "Update failed", description: err.message, variant: "destructive" });
    },
  });

  const prompts = promptsData?.data?.prompts || [];
  const categories = categoriesData?.data || [];
  const totalPrompts = promptsData?.data?.total || 0;
  const activePrompts = prompts.filter((p) => p.isActive);

  const typeGroups = activePrompts.reduce((acc, p) => {
    acc[p.promptType] = (acc[p.promptType] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  const handleCopy = (prompt: Prompt) => {
    navigator.clipboard.writeText(prompt.content);
    setCopiedId(prompt.id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleEdit = (prompt: Prompt) => {
    setEditingPrompt(prompt);
    setEditContent(prompt.content);
    setEditDescription(prompt.description || "");
    setEditType(prompt.promptType);
  };

  const handleSaveEdit = () => {
    if (!editingPrompt) return;
    const payload: any = { id: editingPrompt.id };
    if (editContent !== editingPrompt.content) payload.content = editContent;
    if (editDescription !== (editingPrompt.description || "")) payload.description = editDescription;
    if (editType !== editingPrompt.promptType) payload.promptType = editType;
    updateMutation.mutate(payload);
  };

  const categoryLabel = (cat: string) =>
    cat.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

  const formatTitle = (key: string) =>
    key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

  const getTypeConfig = (type: string) =>
    TYPE_CONFIG[type] || TYPE_CONFIG.template;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <p className="text-sm text-muted-foreground">Loading prompts...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="prompt-management-tab">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">Prompt Management</h2>
          <p className="text-sm text-muted-foreground mt-1">
            View and edit AI prompt templates used across the application.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {Object.entries(typeGroups).map(([type, count]) => {
            const cfg = getTypeConfig(type);
            const Icon = cfg.icon;
            return (
              <div key={type} className={cn("flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-medium", cfg.color)}>
                <Icon className="h-3 w-3" />
                {count} {cfg.label}
              </div>
            );
          })}
          <Badge variant="secondary" className="ml-1" data-testid="badge-prompt-count">
            <Layers className="h-3 w-3 mr-1" />
            {totalPrompts} total
          </Badge>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        <div className="lg:col-span-1 space-y-3">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground px-1">
            <Filter className="h-3 w-3" />
            Categories
          </div>
          <div className="space-y-0.5">
            <button
              onClick={() => setSelectedCategory("all")}
              className={cn(
                "w-full text-left px-3 py-2.5 rounded-lg text-sm transition-all flex items-center justify-between group",
                selectedCategory === "all"
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "hover:bg-muted/80 text-foreground"
              )}
              data-testid="category-all"
            >
              <span className="font-medium">All Prompts</span>
              <span className={cn(
                "text-xs tabular-nums px-1.5 py-0.5 rounded-md",
                selectedCategory === "all"
                  ? "bg-primary-foreground/20"
                  : "bg-muted text-muted-foreground"
              )}>
                {totalPrompts}
              </span>
            </button>
            {categories.map((cat) => (
              <button
                key={cat.name}
                onClick={() => setSelectedCategory(cat.name)}
                className={cn(
                  "w-full text-left px-3 py-2.5 rounded-lg text-sm transition-all flex items-center justify-between group",
                  selectedCategory === cat.name
                    ? "bg-primary text-primary-foreground shadow-sm"
                    : "hover:bg-muted/80 text-foreground"
                )}
                data-testid={`category-${cat.name}`}
              >
                <span className="font-medium truncate">{categoryLabel(cat.name)}</span>
                <span className={cn(
                  "text-xs tabular-nums px-1.5 py-0.5 rounded-md",
                  selectedCategory === cat.name
                    ? "bg-primary-foreground/20"
                    : "bg-muted text-muted-foreground"
                )}>
                  {cat.activeCount}
                </span>
              </button>
            ))}
          </div>
        </div>

        <div className="lg:col-span-4 space-y-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search by prompt key or content..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10 h-10"
              data-testid="input-search-prompts"
            />
          </div>

          {activePrompts.length === 0 ? (
            <Card className="border-dashed">
              <CardContent className="py-12 text-center">
                <FileText className="h-10 w-10 text-muted-foreground/40 mx-auto mb-3" />
                <p className="text-sm font-medium text-muted-foreground">No prompts found</p>
                <p className="text-xs text-muted-foreground/70 mt-1">Try adjusting your search or category filter.</p>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-2">
              {activePrompts.map((prompt) => {
                const isExpanded = expandedPrompt === prompt.id;
                const typeCfg = getTypeConfig(prompt.promptType);
                const TypeIcon = typeCfg.icon;

                return (
                  <Card
                    key={prompt.id}
                    className={cn(
                      "transition-all overflow-hidden",
                      isExpanded && "ring-1 ring-primary/20"
                    )}
                    data-testid={`prompt-card-${prompt.id}`}
                  >
                    <div
                      className="flex items-start gap-4 px-4 py-3 cursor-pointer hover:bg-muted/40 transition-colors"
                      onClick={() => setExpandedPrompt(isExpanded ? null : prompt.id)}
                      data-testid={`prompt-toggle-${prompt.id}`}
                    >
                      <div className={cn("mt-0.5 p-1.5 rounded-md border shrink-0", typeCfg.color)}>
                        <TypeIcon className="h-3.5 w-3.5" />
                      </div>

                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-semibold truncate" data-testid={`prompt-key-${prompt.id}`}>
                            {formatTitle(prompt.promptKey)}
                          </p>
                          <Badge variant="outline" className="text-[10px] px-1.5 py-0 shrink-0 font-mono">
                            v{prompt.version}
                          </Badge>
                        </div>
                        <p className="text-xs text-muted-foreground/60 font-mono mt-0.5">
                          {prompt.promptKey}
                        </p>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          {prompt.description || (
                            <span className="italic text-muted-foreground/50">No description</span>
                          )}
                        </p>
                      </div>

                      <div className="flex items-center gap-2 shrink-0 mt-0.5">
                        <div className={cn("text-[10px] font-medium px-2 py-0.5 rounded-full border", typeCfg.color)}>
                          {typeCfg.label}
                        </div>
                        <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                          {categoryLabel(prompt.category)}
                        </Badge>
                        {isExpanded ? (
                          <ChevronUp className="h-4 w-4 text-muted-foreground" />
                        ) : (
                          <ChevronDown className="h-4 w-4 text-muted-foreground" />
                        )}
                      </div>
                    </div>

                    {isExpanded && (
                      <div className="border-t bg-muted/20">
                        <div className="px-4 py-3 space-y-3">
                          <div className="flex items-center gap-4 text-xs text-muted-foreground">
                            <span className="flex items-center gap-1">
                              <Hash className="h-3 w-3" />
                              {prompt.category}/{prompt.promptKey}
                            </span>
                            <span className="flex items-center gap-1">
                              <History className="h-3 w-3" />
                              {prompt.updatedAt
                                ? new Date(prompt.updatedAt).toLocaleDateString("en-US", {
                                    year: "numeric", month: "short", day: "numeric"
                                  })
                                : "Never updated"}
                            </span>
                          </div>
                          <pre
                            className="text-xs bg-background border rounded-lg p-4 overflow-x-auto whitespace-pre-wrap max-h-72 overflow-y-auto font-mono leading-relaxed"
                            data-testid={`prompt-content-${prompt.id}`}
                          >
                            {prompt.content}
                          </pre>
                          <div className="flex items-center justify-end gap-2">
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-8 text-xs"
                              onClick={(e) => {
                                e.stopPropagation();
                                handleCopy(prompt);
                              }}
                              data-testid={`button-copy-${prompt.id}`}
                            >
                              {copiedId === prompt.id ? (
                                <Check className="h-3.5 w-3.5 mr-1.5 text-green-500" />
                              ) : (
                                <Copy className="h-3.5 w-3.5 mr-1.5" />
                              )}
                              {copiedId === prompt.id ? "Copied!" : "Copy"}
                            </Button>
                            <Button
                              variant="outline"
                              size="sm"
                              className="h-8 text-xs"
                              onClick={(e) => {
                                e.stopPropagation();
                                handleEdit(prompt);
                              }}
                              data-testid={`button-edit-${prompt.id}`}
                            >
                              <Pencil className="h-3.5 w-3.5 mr-1.5" />
                              Edit Prompt
                            </Button>
                          </div>
                        </div>
                      </div>
                    )}
                  </Card>
                );
              })}
            </div>
          )}
        </div>
      </div>

      <Dialog open={!!editingPrompt} onOpenChange={(open) => !open && setEditingPrompt(null)}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base">
              <Pencil className="h-4 w-4" />
              Edit Prompt
            </DialogTitle>
          </DialogHeader>
          {editingPrompt && (
            <div className="space-y-5">
              <div className="flex items-center gap-2 flex-wrap">
                <Badge variant="secondary">{categoryLabel(editingPrompt.category)}</Badge>
                <Badge variant="outline" className="font-mono">{editingPrompt.promptKey}</Badge>
                <Badge variant="outline">v{editingPrompt.version}</Badge>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="edit-description" className="text-xs font-medium">Description</Label>
                  <Input
                    id="edit-description"
                    value={editDescription}
                    onChange={(e) => setEditDescription(e.target.value)}
                    placeholder="Brief description of this prompt's purpose"
                    className="h-9 text-sm"
                    data-testid="input-edit-description"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="edit-type" className="text-xs font-medium">Type</Label>
                  <Select value={editType} onValueChange={setEditType}>
                    <SelectTrigger className="h-9 text-sm" data-testid="select-edit-type">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="system">
                        <span className="flex items-center gap-2">
                          <Bot className="h-3.5 w-3.5 text-blue-500" />
                          System
                        </span>
                      </SelectItem>
                      <SelectItem value="user">
                        <span className="flex items-center gap-2">
                          <User className="h-3.5 w-3.5 text-emerald-500" />
                          User
                        </span>
                      </SelectItem>
                      <SelectItem value="template">
                        <span className="flex items-center gap-2">
                          <Code className="h-3.5 w-3.5 text-amber-500" />
                          Template
                        </span>
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="edit-content" className="text-xs font-medium">Prompt Content</Label>
                <p className="text-[11px] text-muted-foreground">
                  {editContent !== editingPrompt.content
                    ? "Content changed — saving will create a new version (v" + (editingPrompt.version + 1) + ")."
                    : "Modify the prompt content below. Changing content creates a new version."}
                </p>
                <Textarea
                  id="edit-content"
                  value={editContent}
                  onChange={(e) => setEditContent(e.target.value)}
                  className="min-h-[300px] font-mono text-xs leading-relaxed"
                  data-testid="textarea-edit-prompt"
                />
              </div>
            </div>
          )}
          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="ghost" onClick={() => setEditingPrompt(null)} data-testid="button-cancel-edit">
              Cancel
            </Button>
            <Button
              onClick={handleSaveEdit}
              disabled={
                updateMutation.isPending ||
                (editContent === editingPrompt?.content &&
                 editDescription === (editingPrompt?.description || "") &&
                 editType === editingPrompt?.promptType)
              }
              data-testid="button-save-prompt"
            >
              {updateMutation.isPending && (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              )}
              {editContent !== editingPrompt?.content
                ? `Save as v${(editingPrompt?.version || 0) + 1}`
                : "Save Changes"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
