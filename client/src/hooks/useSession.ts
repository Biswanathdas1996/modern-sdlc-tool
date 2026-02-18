import { createContext, useContext, useState, useCallback } from "react";
import {
  generateSessionId,
  createSession as createStorageSession,
  getCurrentSession,
  saveSessionData as saveData,
  getSessionData as getData,
  clearSessionData as clearData,
  type WorkflowSession,
  type SessionArtifact,
} from "@/lib/localStorageCache";

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
  const [session, setSession] = useState<WorkflowSession | null>(() => getCurrentSession());

  const startSession = useCallback((meta?: Partial<WorkflowSession>) => {
    const sessionId = generateSessionId();
    const newSession = createStorageSession(sessionId, meta);
    setSession(newSession);
    return sessionId;
  }, []);

  const getSessionArtifact = useCallback(<T,>(artifact: SessionArtifact): T | null => {
    const currentSession = session || getCurrentSession();
    if (!currentSession) return null;
    return getData<T>(currentSession.sessionId, artifact);
  }, [session]);

  const saveSessionArtifact = useCallback(<T,>(artifact: SessionArtifact, data: T): void => {
    let currentSession = session;
    if (!currentSession) {
      const sid = generateSessionId();
      currentSession = createStorageSession(sid);
      setSession(currentSession);
    }
    saveData(currentSession.sessionId, artifact, data);
  }, [session]);

  const clearSession = useCallback(() => {
    if (session) {
      clearData(session.sessionId);
    }
    setSession(null);
    localStorage.removeItem("docugen_session_current");
  }, [session]);

  const refreshSession = useCallback(() => {
    setSession(getCurrentSession());
  }, []);

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
