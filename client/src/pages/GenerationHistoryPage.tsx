import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  History,
  ChevronDown,
  ChevronRight,
  FileCheck,
  Bookmark,
  TestTube,
  Database,
  ClipboardList,
  Lightbulb,
  Bug,
  RefreshCw,
  Calendar,
  Hash,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useProject } from "@/hooks/useProject";
import { EmptyState } from "@/components/EmptyState";
import { LoadingSpinner } from "@/components/LoadingSpinner";

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
  feature: { label: "Feature", icon: Lightbulb, color: "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/30" },
  bug: { label: "Bug", icon: Bug, color: "bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/30" },
  change_request: { label: "Change Request", icon: RefreshCw, color: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30" },
  enhancement: { label: "Enhancement", icon: RefreshCw, color: "bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/30" },
};

function formatDate(dateStr: string) {
  if (!dateStr) return "";
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

function SummaryBadge({ count, label, icon: Icon }: { count: number; label: string; icon: typeof FileCheck }) {
  if (count === 0) return null;
  return (
    <div className="flex items-center gap-1.5 text-xs text-muted-foreground" data-testid={`badge-${label.toLowerCase().replace(/\s/g, "-")}`}>
      <Icon className="h-3.5 w-3.5" />
      <span className="font-medium">{count}</span>
      <span>{label}{count !== 1 ? "s" : ""}</span>
    </div>
  );
}

function BrdSection({ brd }: { brd: BrdItem }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border rounded-lg bg-card" data-testid={`brd-card-${brd.id}`}>
      <button
        className="w-full flex items-center gap-3 p-3 text-left hover:bg-muted/50 transition-colors rounded-lg"
        onClick={() => setExpanded(!expanded)}
        data-testid={`button-expand-brd-${brd.id}`}
      >
        {expanded ? <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" /> : <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />}
        <FileCheck className="h-4 w-4 shrink-0 text-primary" />
        <div className="flex-1 min-w-0">
          <p className="font-medium text-sm truncate">{brd.title}</p>
          <div className="flex items-center gap-2 text-xs text-muted-foreground mt-0.5">
            <span>v{brd.version}</span>
            <span>•</span>
            <Calendar className="h-3 w-3" />
            <span>{formatDate(brd.createdAt)}</span>
          </div>
        </div>
        <Badge variant="outline" className="text-xs shrink-0">
          {brd.status}
        </Badge>
      </button>

      {expanded && (
        <div className="px-3 pb-3 space-y-3">
          <div className="flex flex-wrap gap-3 pl-8">
            <SummaryBadge count={brd.userStoryCount} label="User Story" icon={Bookmark} />
            <SummaryBadge count={brd.testCaseCount} label="Test Case" icon={TestTube} />
            <SummaryBadge count={brd.testDataCount} label="Test Data" icon={Database} />
          </div>

          {brd.userStories.length > 0 && (
            <div className="pl-8 space-y-1.5">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide flex items-center gap-1.5">
                <Bookmark className="h-3 w-3" /> User Stories
              </p>
              {brd.userStories.map((story: any, idx: number) => (
                <div key={story.id || idx} className="flex items-center gap-2 text-xs p-2 rounded bg-muted/30" data-testid={`story-item-${story.id}`}>
                  <Hash className="h-3 w-3 text-muted-foreground shrink-0" />
                  <span className="truncate flex-1">{story.title}</span>
                  {story.priority && (
                    <Badge variant="outline" className="text-[10px] py-0 px-1.5">{story.priority}</Badge>
                  )}
                </div>
              ))}
            </div>
          )}

          {brd.testCases.length > 0 && (
            <div className="pl-8 space-y-1.5">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide flex items-center gap-1.5">
                <TestTube className="h-3 w-3" /> Test Cases
              </p>
              {brd.testCases.map((tc: any, idx: number) => (
                <div key={tc.id || idx} className="flex items-center gap-2 text-xs p-2 rounded bg-muted/30" data-testid={`testcase-item-${tc.id}`}>
                  <Hash className="h-3 w-3 text-muted-foreground shrink-0" />
                  <span className="truncate flex-1">{tc.title}</span>
                  {tc.category && (
                    <Badge variant="outline" className="text-[10px] py-0 px-1.5">{tc.category}</Badge>
                  )}
                  {tc.priority && (
                    <Badge variant="outline" className="text-[10px] py-0 px-1.5">{tc.priority}</Badge>
                  )}
                </div>
              ))}
            </div>
          )}

          {brd.testData.length > 0 && (
            <div className="pl-8 space-y-1.5">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide flex items-center gap-1.5">
                <Database className="h-3 w-3" /> Test Data
              </p>
              {brd.testData.map((td: any, idx: number) => (
                <div key={td.id || idx} className="flex items-center gap-2 text-xs p-2 rounded bg-muted/30" data-testid={`testdata-item-${td.id}`}>
                  <Hash className="h-3 w-3 text-muted-foreground shrink-0" />
                  <span className="truncate flex-1">{td.name}</span>
                  {td.dataType && (
                    <Badge variant="outline" className="text-[10px] py-0 px-1.5">{td.dataType}</Badge>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function GenerationHistoryPage() {
  const { currentProjectId } = useProject();
  const [expandedFRs, setExpandedFRs] = useState<Set<string>>(new Set());

  const { data: history, isLoading } = useQuery<HistoryGroup[]>({
    queryKey: [`/api/generation-history?project_id=${currentProjectId}`],
    enabled: !!currentProjectId,
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

  return (
    <div className="flex flex-col h-full">
      <div className="border-b bg-card/50">
        <div className="p-6">
          <div className="flex items-center gap-3 mb-2">
            <div className="flex h-10 w-10 items-center justify-center rounded-md bg-primary">
              <History className="h-5 w-5 text-primary-foreground" />
            </div>
            <div>
              <h1 className="text-2xl font-bold" data-testid="text-page-title">Generation History</h1>
              <p className="text-sm text-muted-foreground">
                All generated artifacts grouped by feature request
              </p>
            </div>
          </div>
          {totalFRs > 0 && (
            <div className="flex gap-4 mt-4">
              <Badge variant="outline" className="text-sm" data-testid="badge-total-frs">
                {totalFRs} Feature Request{totalFRs !== 1 ? "s" : ""}
              </Badge>
              <Badge variant="outline" className="text-sm" data-testid="badge-total-brds">
                {totalBRDs} BRD{totalBRDs !== 1 ? "s" : ""}
              </Badge>
              <Badge variant="outline" className="text-sm" data-testid="badge-total-stories">
                {totalStories} User Stor{totalStories !== 1 ? "ies" : "y"}
              </Badge>
            </div>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-auto p-6">
        <div className="max-w-4xl mx-auto">
          {isLoading ? (
            <div className="flex items-center justify-center py-20">
              <LoadingSpinner />
            </div>
          ) : !history || history.length === 0 ? (
            <EmptyState
              icon="document"
              title="No generation history"
              description="Start by creating a feature request, then generate BRDs, user stories, test cases, and test data."
            />
          ) : (
            <ScrollArea className="h-[calc(100vh-220px)]">
              <div className="space-y-4">
                {history.map((group) => {
                  const fr = group.featureRequest;
                  const isExpanded = expandedFRs.has(fr.id);
                  const typeConfig = requestTypeConfig[fr.requestType] || requestTypeConfig.feature;
                  const TypeIcon = typeConfig.icon;

                  return (
                    <Card key={fr.id} className="overflow-hidden" data-testid={`fr-card-${fr.id}`}>
                      <button
                        className="w-full flex items-start gap-4 p-5 text-left hover:bg-muted/30 transition-colors"
                        onClick={() => toggleFR(fr.id)}
                        data-testid={`button-expand-fr-${fr.id}`}
                      >
                        <div className="mt-0.5">
                          {isExpanded ? (
                            <ChevronDown className="h-5 w-5 text-muted-foreground" />
                          ) : (
                            <ChevronRight className="h-5 w-5 text-muted-foreground" />
                          )}
                        </div>
                        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-primary/10">
                          <ClipboardList className="h-5 w-5 text-primary" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <p className="font-semibold truncate">{fr.title}</p>
                            <Badge variant="outline" className={`text-xs shrink-0 ${typeConfig.color}`}>
                              <TypeIcon className="h-3 w-3 mr-1" />
                              {typeConfig.label}
                            </Badge>
                          </div>
                          {fr.description && (
                            <p className="text-sm text-muted-foreground line-clamp-2 mb-2">{fr.description}</p>
                          )}
                          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                            <Calendar className="h-3 w-3" />
                            <span>{formatDate(fr.createdAt)}</span>
                          </div>
                        </div>
                        <div className="flex flex-wrap gap-3 shrink-0">
                          <SummaryBadge count={group.summary.brdCount} label="BRD" icon={FileCheck} />
                          <SummaryBadge count={group.summary.userStoryCount} label="Story" icon={Bookmark} />
                          <SummaryBadge count={group.summary.testCaseCount} label="Test" icon={TestTube} />
                          <SummaryBadge count={group.summary.testDataCount} label="Data" icon={Database} />
                        </div>
                      </button>

                      {isExpanded && (
                        <CardContent className="pt-0 pb-4 px-5">
                          <div className="ml-14 space-y-2">
                            {group.brds.length === 0 ? (
                              <p className="text-sm text-muted-foreground italic py-2">No BRDs generated yet</p>
                            ) : (
                              group.brds.map((brd) => (
                                <BrdSection key={brd.id} brd={brd} />
                              ))
                            )}
                          </div>
                        </CardContent>
                      )}
                    </Card>
                  );
                })}
              </div>
            </ScrollArea>
          )}
        </div>
      </div>
    </div>
  );
}
