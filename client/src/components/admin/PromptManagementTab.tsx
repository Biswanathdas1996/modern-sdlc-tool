import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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

export default function PromptManagementTab() {
  const { toast } = useToast();
  const [selectedCategory, setSelectedCategory] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [expandedPrompt, setExpandedPrompt] = useState<string | null>(null);
  const [editingPrompt, setEditingPrompt] = useState<Prompt | null>(null);
  const [editContent, setEditContent] = useState("");
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
    mutationFn: async ({
      id,
      content,
    }: {
      id: string;
      content: string;
    }) => {
      const res = await apiRequest("PUT", `/api/prompts/${id}`, { content });
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/prompts"] });
      queryClient.invalidateQueries({ queryKey: ["/api/prompts-categories"] });
      setEditingPrompt(null);
      toast({ title: "Prompt updated", description: "New version created successfully" });
    },
    onError: (err: any) => {
      toast({ title: "Update failed", description: err.message, variant: "destructive" });
    },
  });

  const prompts = promptsData?.data?.prompts || [];
  const categories = categoriesData?.data || [];
  const totalPrompts = promptsData?.data?.total || 0;

  const activePrompts = prompts.filter((p) => p.isActive);

  const handleCopy = (prompt: Prompt) => {
    navigator.clipboard.writeText(prompt.content);
    setCopiedId(prompt.id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleEdit = (prompt: Prompt) => {
    setEditingPrompt(prompt);
    setEditContent(prompt.content);
  };

  const handleSaveEdit = () => {
    if (!editingPrompt) return;
    updateMutation.mutate({
      id: editingPrompt.id,
      content: editContent,
    });
  };

  const categoryLabel = (cat: string) =>
    cat
      .replace(/_/g, " ")
      .replace(/\b\w/g, (c) => c.toUpperCase());

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-4" data-testid="prompt-management-tab">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Manage AI prompt templates used across the application. Edit prompts to customize AI behavior.
        </p>
        <Badge variant="outline" data-testid="badge-prompt-count">{totalPrompts} prompts</Badge>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card className="col-span-1">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <Tag className="h-4 w-4" />
              Categories
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1">
            <button
              onClick={() => setSelectedCategory("all")}
              className={cn(
                "w-full text-left px-3 py-2 rounded-md text-sm transition-colors",
                selectedCategory === "all"
                  ? "bg-primary text-primary-foreground"
                  : "hover:bg-muted"
              )}
              data-testid="category-all"
            >
              All ({totalPrompts})
            </button>
            {categories.map((cat) => (
              <button
                key={cat.name}
                onClick={() => setSelectedCategory(cat.name)}
                className={cn(
                  "w-full text-left px-3 py-2 rounded-md text-sm transition-colors",
                  selectedCategory === cat.name
                    ? "bg-primary text-primary-foreground"
                    : "hover:bg-muted"
                )}
                data-testid={`category-${cat.name}`}
              >
                {categoryLabel(cat.name)} ({cat.activeCount})
              </button>
            ))}
          </CardContent>
        </Card>

        <div className="col-span-1 md:col-span-3 space-y-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search prompts by key or content..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10"
              data-testid="input-search-prompts"
            />
          </div>

          <div className="space-y-2">
            {activePrompts.length === 0 ? (
              <Card>
                <CardContent className="py-8 text-center text-muted-foreground">
                  No prompts found matching your criteria.
                </CardContent>
              </Card>
            ) : (
              activePrompts.map((prompt) => (
                <Card
                  key={prompt.id}
                  className="overflow-hidden"
                  data-testid={`prompt-card-${prompt.id}`}
                >
                  <div
                    className="flex items-center justify-between px-4 py-3 cursor-pointer hover:bg-muted/50 transition-colors"
                    onClick={() =>
                      setExpandedPrompt(
                        expandedPrompt === prompt.id ? null : prompt.id
                      )
                    }
                    data-testid={`prompt-toggle-${prompt.id}`}
                  >
                    <div className="flex items-center gap-3 min-w-0 flex-1">
                      <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
                      <div className="min-w-0">
                        <p className="text-sm font-medium truncate" data-testid={`prompt-key-${prompt.id}`}>
                          {prompt.promptKey}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {categoryLabel(prompt.category)}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <Badge
                        variant="outline"
                        className="text-xs"
                      >
                        v{prompt.version}
                      </Badge>
                      <Badge
                        variant="outline"
                        className="text-xs"
                      >
                        {prompt.promptType}
                      </Badge>
                      {expandedPrompt === prompt.id ? (
                        <ChevronUp className="h-4 w-4 text-muted-foreground" />
                      ) : (
                        <ChevronDown className="h-4 w-4 text-muted-foreground" />
                      )}
                    </div>
                  </div>

                  {expandedPrompt === prompt.id && (
                    <div className="border-t px-4 py-3 space-y-3">
                      <pre className="text-xs bg-muted p-3 rounded-md overflow-x-auto whitespace-pre-wrap max-h-64 overflow-y-auto font-mono" data-testid={`prompt-content-${prompt.id}`}>
                        {prompt.content}
                      </pre>
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 text-xs text-muted-foreground">
                          <History className="h-3 w-3" />
                          {prompt.updatedAt
                            ? `Updated ${new Date(prompt.updatedAt).toLocaleDateString()}`
                            : "No updates"}
                        </div>
                        <div className="flex items-center gap-2">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleCopy(prompt);
                            }}
                            data-testid={`button-copy-${prompt.id}`}
                          >
                            {copiedId === prompt.id ? (
                              <Check className="h-3 w-3 mr-1" />
                            ) : (
                              <Copy className="h-3 w-3 mr-1" />
                            )}
                            {copiedId === prompt.id ? "Copied" : "Copy"}
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleEdit(prompt);
                            }}
                            data-testid={`button-edit-${prompt.id}`}
                          >
                            <Pencil className="h-3 w-3 mr-1" />
                            Edit
                          </Button>
                        </div>
                      </div>
                    </div>
                  )}
                </Card>
              ))
            )}
          </div>
        </div>
      </div>

      <Dialog open={!!editingPrompt} onOpenChange={(open) => !open && setEditingPrompt(null)}>
        <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Pencil className="h-4 w-4" />
              Edit Prompt
            </DialogTitle>
          </DialogHeader>
          {editingPrompt && (
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                <Badge variant="outline">{categoryLabel(editingPrompt.category)}</Badge>
                <Badge variant="outline">{editingPrompt.promptKey}</Badge>
                <Badge variant="outline">v{editingPrompt.version}</Badge>
              </div>
              <p className="text-xs text-muted-foreground">
                Saving will create a new version (v{editingPrompt.version + 1}) and deactivate the current one.
              </p>
              <Textarea
                value={editContent}
                onChange={(e) => setEditContent(e.target.value)}
                className="min-h-[300px] font-mono text-xs"
                data-testid="textarea-edit-prompt"
              />
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditingPrompt(null)} data-testid="button-cancel-edit">
              Cancel
            </Button>
            <Button
              onClick={handleSaveEdit}
              disabled={
                updateMutation.isPending ||
                editContent === editingPrompt?.content
              }
              data-testid="button-save-prompt"
            >
              {updateMutation.isPending && (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              )}
              Save as v{(editingPrompt?.version || 0) + 1}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
