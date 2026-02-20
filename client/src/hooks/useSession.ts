import { createContext, useContext, useState, useCallback, useEffect, useRef } from "react";
import { useProject } from "@/hooks/useProject";
import { apiRequest } from "@/lib/queryClient";

export type SessionArtifact = "project" | "documentation" | "analysis" | "featureRequest" | "brd" | "userStories" | "testCases" | "testData" | "bpmn" | "databaseSchema" | "copilotPrompt";

export interface WorkflowSession {
  sessionId: string;
  id?: string;
  createdAt: number;
  projectName?: string;
  requestType?: string;
  featureTitle?: string;
}

interface SessionContextValue {
  session: WorkflowSession | null;
  startSession: (meta?: Partial<WorkflowSession>) => string;
  getSessionArtifact: <T>(artifact: SessionArtifact) => T | null;
  saveSessionArtifact: <T>(artifact: SessionArtifact, data: T) => void;
  clearSession: () => void;
  refreshSession: () => void;
}

export const SessionContext = createContext<SessionContextValue | null>(null);

export function useSessionProvider(): SessionContextValue {
  const { currentProjectId } = useProject();
  const [session, setSession] = useState<WorkflowSession | null>(null);
  const artifactCache = useRef<Record<string, any>>({});
  const sessionRef = useRef<WorkflowSession | null>(null);
  const pendingSessionPromise = useRef<Promise<string> | null>(null);
  const pendingArtifacts = useRef<Array<{ artifact: SessionArtifact; data: any }>>([]);

  useEffect(() => {
    if (!currentProjectId) return;
    pendingArtifacts.current = [];
    pendingSessionPromise.current = null;
    fetch(`/api/sessions/active?project_id=${currentProjectId}`, { credentials: "include" })
      .then(res => res.ok ? res.json() : null)
      .then(data => {
        if (data?.session) {
          const s = data.session;
          const ws: WorkflowSession = {
            sessionId: s.id,
            id: s.id,
            createdAt: new Date(s.created_at).getTime(),
            projectName: s.label,
            requestType: s.request_type,
            featureTitle: s.feature_title,
          };
          setSession(ws);
          sessionRef.current = ws;
          artifactCache.current = data.artifacts || {};
        } else {
          setSession(null);
          sessionRef.current = null;
          artifactCache.current = {};
        }
      })
      .catch(() => {});
  }, [currentProjectId]);

  const startSession = useCallback((meta?: Partial<WorkflowSession>) => {
    const tempId = `sess_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
    artifactCache.current = {};
    pendingArtifacts.current = [];

    if (!currentProjectId) return tempId;

    const promise = apiRequest("POST", "/api/sessions", {
      project_id: currentProjectId,
      label: meta?.projectName || null,
      request_type: meta?.requestType || null,
      feature_title: meta?.featureTitle || null,
    })
      .then(res => res.json())
      .then(data => {
        const ws: WorkflowSession = {
          sessionId: data.id,
          id: data.id,
          createdAt: new Date(data.created_at).getTime(),
          projectName: data.label,
          requestType: data.request_type,
          featureTitle: data.feature_title,
        };
        setSession(ws);
        sessionRef.current = ws;
        pendingSessionPromise.current = null;

        const queued = [...pendingArtifacts.current];
        pendingArtifacts.current = [];
        for (const { artifact, data: payload } of queued) {
          apiRequest("POST", `/api/sessions/${data.id}/artifacts`, {
            artifact_type: artifact,
            payload,
          }).catch(err => console.error(`Failed to save queued artifact [${artifact}]:`, err));
        }

        return data.id as string;
      })
      .catch(err => {
        console.error("Failed to create session:", err);
        pendingSessionPromise.current = null;
        return tempId;
      });

    pendingSessionPromise.current = promise;
    return tempId;
  }, [currentProjectId]);

  const getSessionArtifact = useCallback(<T,>(artifact: SessionArtifact): T | null => {
    const cached = artifactCache.current[artifact];
    return cached !== undefined ? (cached as T) : null;
  }, []);

  const saveSessionArtifact = useCallback(<T,>(artifact: SessionArtifact, data: T): void => {
    artifactCache.current[artifact] = data;

    if (pendingSessionPromise.current) {
      pendingArtifacts.current.push({ artifact, data });
      return;
    }

    const sid = sessionRef.current?.sessionId || sessionRef.current?.id;
    if (!sid) return;

    apiRequest("POST", `/api/sessions/${sid}/artifacts`, {
      artifact_type: artifact,
      payload: data,
    }).catch(err => console.error(`Failed to save artifact [${artifact}]:`, err));
  }, []);

  const clearSession = useCallback(() => {
    const sid = sessionRef.current?.sessionId || sessionRef.current?.id;
    if (sid) {
      apiRequest("DELETE", `/api/sessions/${sid}`).catch(() => {});
    }
    setSession(null);
    sessionRef.current = null;
    artifactCache.current = {};
    pendingArtifacts.current = [];
    pendingSessionPromise.current = null;
  }, []);

  const refreshSession = useCallback(() => {
    if (!currentProjectId) return;
    fetch(`/api/sessions/active?project_id=${currentProjectId}`, { credentials: "include" })
      .then(res => res.ok ? res.json() : null)
      .then(data => {
        if (data?.session) {
          const s = data.session;
          const ws: WorkflowSession = {
            sessionId: s.id,
            id: s.id,
            createdAt: new Date(s.created_at).getTime(),
            projectName: s.label,
            requestType: s.request_type,
            featureTitle: s.feature_title,
          };
          setSession(ws);
          sessionRef.current = ws;
          artifactCache.current = data.artifacts || {};
        }
      })
      .catch(() => {});
  }, [currentProjectId]);

  return {
    session,
    startSession,
    getSessionArtifact,
    saveSessionArtifact,
    clearSession,
    refreshSession,
  };
}

export function useSession(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) {
    throw new Error("useSession must be used within a SessionProvider");
  }
  return ctx;
}
