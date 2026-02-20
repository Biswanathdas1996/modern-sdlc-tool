import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  History,
  ChevronDown,
  ChevronRight,
  FileCheck,
  Bookmark,
  TestTube,
  Database,
  Lightbulb,
  Bug,
  RefreshCw,
  Calendar,
  Trash2,
  AlertTriangle,
  Eye,
} from "lucide-react";
import { useLocation } from "wouter";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useProject } from "@/hooks/useProject";
import { useToast } from "@/hooks/use-toast";
import { EmptyState } from "@/components/EmptyState";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { apiRequest } from "@/lib/queryClient";
import { cn } from "@/lib/utils";

interface FeatureRequestSummary {
  id: string;
  title: string;
  description: string;
  requestType: string;
  createdAt: string;
}

interface BrdItem {
  id: string;
  title: string;
  version: string;
  status: string;
  createdAt: string;
  userStoryCount: number;
  testCaseCount: number;
  testDataCount: number;
  userStories: any[];
  testCases: any[];
  testData: any[];
}

interface HistoryGroup {
  featureRequest: FeatureRequestSummary;
  summary: {
    brdCount: number;
    userStoryCount: number;
    testCaseCount: number;
    testDataCount: number;
  };
  brds: BrdItem[];
}

const requestTypeConfig: Record<string, { label: string; icon: typeof Lightbulb; color: string }> = {
  feature: { label: "Feature", icon: Lightbulb, color: "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20" },
  bug: { label: "Bug", icon: Bug, color: "bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/20" },
  change_request: { label: "Change", icon: RefreshCw, color: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20" },
  enhancement: { label: "Enhancement", icon: RefreshCw, color: "bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/20" },
};

function formatDate(dateStr: string) {
  if (!dateStr) return "—";
  try {
    return new Date(dateStr).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return dateStr;
  }
}

function CountPill({ count, label, icon: Icon, className }: { count: number; label: string; icon: typeof FileCheck; className?: string }) {
  return (
    <div className={cn("inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium", className)} data-testid={`count-${label.toLowerCase()}`}>
      <Icon className="h-3 w-3" />
      <span>{count}</span>
      <span className="hidden sm:inline">{label}</span>
    </div>
  );
}

function ExpandedBrdRow({ brd }: { brd: BrdItem }) {
  const [showDetails, setShowDetails] = useState(false);
  const [, navigate] = useLocation();

  return (
    <>
      <tr
        className="border-b border-border/50 bg-muted/20 hover:bg-muted/40 cursor-pointer transition-colors group/brd"
        onClick={() => setShowDetails(!showDetails)}
        data-testid={`row-brd-${brd.id}`}
      >
        <td className="py-2.5 pl-12 pr-3">
          <div className="flex items-center gap-2">
            {showDetails ? <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" /> : <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />}
            <FileCheck className="h-3.5 w-3.5 text-primary" />
            <span className="text-sm">{brd.title}</span>
          </div>
        </td>
        <td className="py-2.5 px-3">
          <Badge variant="outline" className="text-[10px]">{brd.status}</Badge>
        </td>
        <td className="py-2.5 px-3">
          <span className="text-xs text-muted-foreground">v{brd.version}</span>
        </td>
        <td className="py-2.5 px-3">
          <div className="flex items-center gap-2">
            <CountPill count={brd.userStoryCount} label="Stories" icon={Bookmark} className="bg-indigo-500/10 text-indigo-600 dark:text-indigo-400" />
            <CountPill count={brd.testCaseCount} label="Tests" icon={TestTube} className="bg-emerald-500/10 text-emerald-600 dark:text-emerald-400" />
            <CountPill count={brd.testDataCount} label="Data" icon={Database} className="bg-orange-500/10 text-orange-600 dark:text-orange-400" />
          </div>
        </td>
        <td className="py-2.5 px-3 text-xs text-muted-foreground">{formatDate(brd.createdAt)}</td>
        <td className="py-2.5 px-3 text-right">
          <Button
            size="sm"
            variant="ghost"
            className="text-primary opacity-0 group-hover/brd:opacity-100 transition-opacity h-7 px-2 text-xs"
            onClick={(e) => { e.stopPropagation(); navigate(`/brd?brd_id=${brd.id}`); }}
            data-testid={`button-view-brd-${brd.id}`}
          >
            <Eye className="h-3.5 w-3.5 mr-1" />
            View
          </Button>
        </td>
      </tr>
      {showDetails && (
        <tr className="border-b border-border/30" data-testid={`detail-brd-${brd.id}`}>
          <td colSpan={6} className="py-2 pl-20 pr-4">
            <div className="space-y-3">
              {brd.userStories.length > 0 && (
                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1 flex items-center gap-1">
                    <Bookmark className="h-3 w-3" /> User Stories ({brd.userStoryCount})
                  </p>
                  <div className="grid gap-1">
                    {brd.userStories.map((s: any, i: number) => (
                      <div key={s.id || i} className="flex items-center justify-between text-xs py-1 px-2 rounded bg-muted/30" data-testid={`story-${s.id}`}>
                        <span className="truncate">{s.title}</span>
                        {s.priority && <Badge variant="outline" className="text-[9px] py-0 px-1">{s.priority}</Badge>}
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {brd.testCases.length > 0 && (
                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1 flex items-center gap-1">
                    <TestTube className="h-3 w-3" /> Test Cases ({brd.testCaseCount})
                  </p>
                  <div className="grid gap-1">
                    {brd.testCases.map((tc: any, i: number) => (
                      <div key={tc.id || i} className="flex items-center justify-between text-xs py-1 px-2 rounded bg-muted/30" data-testid={`testcase-${tc.id}`}>
                        <span className="truncate">{tc.title}</span>
                        <div className="flex gap-1">
                          {tc.category && <Badge variant="outline" className="text-[9px] py-0 px-1">{tc.category}</Badge>}
                          {tc.priority && <Badge variant="outline" className="text-[9px] py-0 px-1">{tc.priority}</Badge>}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {brd.testData.length > 0 && (
                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1 flex items-center gap-1">
                    <Database className="h-3 w-3" /> Test Data ({brd.testDataCount})
                  </p>
                  <div className="grid gap-1">
                    {brd.testData.map((td: any, i: number) => (
                      <div key={td.id || i} className="flex items-center justify-between text-xs py-1 px-2 rounded bg-muted/30" data-testid={`testdata-${td.id}`}>
                        <span className="truncate">{td.name}</span>
                        {td.dataType && <Badge variant="outline" className="text-[9px] py-0 px-1">{td.dataType}</Badge>}
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {brd.userStories.length === 0 && brd.testCases.length === 0 && brd.testData.length === 0 && (
                <p className="text-xs text-muted-foreground italic">No child artifacts generated yet</p>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export default function GenerationHistoryPage() {
  const { currentProjectId } = useProject();
  const [expandedFRs, setExpandedFRs] = useState<Set<string>>(new Set());
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const queryKey = [`/api/generation-history?project_id=${currentProjectId}`];

  const { data: history, isLoading } = useQuery<HistoryGroup[]>({
    queryKey,
    enabled: !!currentProjectId,
  });

  const deleteMutation = useMutation({
    mutationFn: async (frId: string) => {
      await apiRequest("DELETE", `/api/feature-request/${frId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey });
      toast({ title: "Deleted", description: "Feature request and all related artifacts have been removed." });
      setDeleteConfirm(null);
    },
    onError: () => {
      toast({ title: "Error", description: "Failed to delete feature request. Please try again.", variant: "destructive" });
    },
  });

  const toggleFR = (id: string) => {
    setExpandedFRs(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const totalFRs = history?.length ?? 0;
  const totalBRDs = history?.reduce((sum, g) => sum + g.summary.brdCount, 0) ?? 0;
  const totalStories = history?.reduce((sum, g) => sum + g.summary.userStoryCount, 0) ?? 0;
  const totalTests = history?.reduce((sum, g) => sum + g.summary.testCaseCount, 0) ?? 0;

  return (
    <div className="flex flex-col h-full">
      <div className="border-b bg-card/50">
        <div className="p-6">
          <div className="flex items-center gap-3 mb-1">
            <div className="flex h-10 w-10 items-center justify-center rounded-md bg-primary">
              <History className="h-5 w-5 text-primary-foreground" />
            </div>
            <div>
              <h1 className="text-2xl font-bold" data-testid="text-page-title">Generation History</h1>
              <p className="text-sm text-muted-foreground">All generated artifacts grouped by feature request</p>
            </div>
          </div>
          {totalFRs > 0 && (
            <div className="flex gap-3 mt-3 ml-[52px]">
              <Badge variant="outline" className="text-xs" data-testid="badge-total-frs">{totalFRs} Requests</Badge>
              <Badge variant="outline" className="text-xs" data-testid="badge-total-brds">{totalBRDs} BRDs</Badge>
              <Badge variant="outline" className="text-xs" data-testid="badge-total-stories">{totalStories} Stories</Badge>
              <Badge variant="outline" className="text-xs" data-testid="badge-total-tests">{totalTests} Tests</Badge>
            </div>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-auto">
        {isLoading ? (
          <div className="flex items-center justify-center py-20">
            <LoadingSpinner />
          </div>
        ) : !history || history.length === 0 ? (
          <div className="p-6">
            <EmptyState
              icon="document"
              title="No generation history"
              description="Start by creating a feature request, then generate BRDs, user stories, test cases, and test data."
            />
          </div>
        ) : (
          <div className="p-4">
            <div className="rounded-lg border border-border overflow-hidden">
              <table className="w-full" data-testid="table-generation-history">
                <thead>
                  <tr className="bg-muted/50 border-b border-border">
                    <th className="text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider py-3 px-4">Feature Request</th>
                    <th className="text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider py-3 px-3">Type</th>
                    <th className="text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider py-3 px-3">Artifacts</th>
                    <th className="text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider py-3 px-3 hidden lg:table-cell">Artifacts Detail</th>
                    <th className="text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider py-3 px-3">Created</th>
                    <th className="text-right text-xs font-semibold text-muted-foreground uppercase tracking-wider py-3 px-4 w-20">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((group) => {
                    const fr = group.featureRequest;
                    const isExpanded = expandedFRs.has(fr.id);
                    const typeConfig = requestTypeConfig[fr.requestType] || requestTypeConfig.feature;
                    const TypeIcon = typeConfig.icon;
                    const isDeleting = deleteConfirm === fr.id;

                    return (
                      <FeatureRequestRows
                        key={fr.id}
                        group={group}
                        isExpanded={isExpanded}
                        isDeleting={isDeleting}
                        typeConfig={typeConfig}
                        TypeIcon={TypeIcon}
                        onToggle={() => toggleFR(fr.id)}
                        onDeleteClick={() => setDeleteConfirm(fr.id)}
                        onDeleteConfirm={() => deleteMutation.mutate(fr.id)}
                        onDeleteCancel={() => setDeleteConfirm(null)}
                        deletePending={deleteMutation.isPending}
                      />
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function FeatureRequestRows({
  group,
  isExpanded,
  isDeleting,
  typeConfig,
  TypeIcon,
  onToggle,
  onDeleteClick,
  onDeleteConfirm,
  onDeleteCancel,
  deletePending,
}: {
  group: HistoryGroup;
  isExpanded: boolean;
  isDeleting: boolean;
  typeConfig: { label: string; color: string };
  TypeIcon: typeof Lightbulb;
  onToggle: () => void;
  onDeleteClick: () => void;
  onDeleteConfirm: () => void;
  onDeleteCancel: () => void;
  deletePending: boolean;
}) {
  const fr = group.featureRequest;
  const s = group.summary;
  const [, navigate] = useLocation();
  const firstBrdId = group.brds.length > 0 ? group.brds[0].id : null;

  return (
    <>
      <tr
        className={cn(
          "border-b border-border transition-colors group",
          isExpanded ? "bg-muted/30" : "hover:bg-muted/20"
        )}
        data-testid={`row-fr-${fr.id}`}
      >
        <td className="py-3 px-4">
          <div className="flex items-center gap-2.5 cursor-pointer" onClick={onToggle} data-testid={`button-toggle-fr-${fr.id}`}>
            {isExpanded ? <ChevronDown className="h-4 w-4 text-muted-foreground shrink-0" /> : <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />}
            <div className="min-w-0">
              <p className="font-medium text-sm truncate" data-testid={`text-fr-title-${fr.id}`}>{fr.title}</p>
              {fr.description && fr.description !== fr.title && (
                <p className="text-xs text-muted-foreground truncate max-w-md">{fr.description}</p>
              )}
            </div>
          </div>
        </td>
        <td className="py-3 px-3">
          <Badge variant="outline" className={cn("text-[10px]", typeConfig.color)}>
            <TypeIcon className="h-3 w-3 mr-0.5" />
            {typeConfig.label}
          </Badge>
        </td>
        <td className="py-3 px-3">
          <div className="flex items-center gap-2 flex-wrap">
            <CountPill count={s.brdCount} label="BRDs" icon={FileCheck} className="bg-sky-500/10 text-sky-600 dark:text-sky-400" />
            <CountPill count={s.userStoryCount} label="Stories" icon={Bookmark} className="bg-indigo-500/10 text-indigo-600 dark:text-indigo-400" />
          </div>
        </td>
        <td className="py-3 px-3 hidden lg:table-cell">
          <div className="flex items-center gap-2 flex-wrap">
            <CountPill count={s.testCaseCount} label="Tests" icon={TestTube} className="bg-emerald-500/10 text-emerald-600 dark:text-emerald-400" />
            <CountPill count={s.testDataCount} label="Data" icon={Database} className="bg-orange-500/10 text-orange-600 dark:text-orange-400" />
          </div>
        </td>
        <td className="py-3 px-3">
          <div className="flex items-center gap-1 text-xs text-muted-foreground">
            <Calendar className="h-3 w-3" />
            <span>{formatDate(fr.createdAt)}</span>
          </div>
        </td>
        <td className="py-3 px-4 text-right">
          {isDeleting ? (
            <div className="flex items-center gap-1 justify-end">
              <Button
                size="sm"
                variant="destructive"
                onClick={onDeleteConfirm}
                disabled={deletePending}
                data-testid={`button-confirm-delete-${fr.id}`}
              >
                {deletePending ? <LoadingSpinner size="sm" /> : "Yes"}
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={onDeleteCancel}
                disabled={deletePending}
                data-testid={`button-cancel-delete-${fr.id}`}
              >
                No
              </Button>
            </div>
          ) : (
            <div className="flex items-center gap-1 justify-end opacity-0 group-hover:opacity-100 transition-opacity">
              {firstBrdId && (
                <Button
                  size="icon"
                  variant="ghost"
                  className="text-primary"
                  onClick={() => navigate(`/brd?brd_id=${firstBrdId}`)}
                  data-testid={`button-view-fr-${fr.id}`}
                >
                  <Eye className="h-4 w-4" />
                </Button>
              )}
              <Button
                size="icon"
                variant="ghost"
                className="text-muted-foreground"
                onClick={onDeleteClick}
                data-testid={`button-delete-fr-${fr.id}`}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          )}
        </td>
      </tr>
      {isDeleting && (
        <tr className="border-b border-border" data-testid={`row-delete-confirm-${fr.id}`}>
          <td colSpan={6} className="py-2 px-4">
            <div className="flex items-center gap-2 text-xs text-destructive bg-destructive/5 rounded-md py-2 px-3">
              <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
              <span>This will permanently delete this feature request and all its BRDs, user stories, test cases, and test data. Are you sure?</span>
            </div>
          </td>
        </tr>
      )}
      {isExpanded && group.brds.length > 0 && group.brds.map((brd) => (
        <ExpandedBrdRow key={brd.id} brd={brd} />
      ))}
      {isExpanded && group.brds.length === 0 && (
        <tr className="border-b border-border/50 bg-muted/10">
          <td colSpan={6} className="py-3 pl-12 pr-4 text-xs text-muted-foreground italic">
            No BRDs generated yet
          </td>
        </tr>
      )}
    </>
  );
}
