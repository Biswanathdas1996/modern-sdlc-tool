const CACHE_PREFIX = "docugen_cache_";
const CACHE_VERSION = "v1";
const SESSION_PREFIX = "docugen_session_";

export function getCacheKey(queryKey: string | string[]): string {
  const key = Array.isArray(queryKey) ? queryKey.join("_") : queryKey;
  return `${CACHE_PREFIX}${CACHE_VERSION}_${key}`;
}

export function getFromCache<T>(queryKey: string | string[]): T | null {
  try {
    const key = getCacheKey(queryKey);
    const cached = localStorage.getItem(key);
    if (cached) {
      const parsed = JSON.parse(cached);
      return parsed.data as T;
    }
  } catch (e) {
    console.warn("Failed to read from cache:", e);
  }
  return null;
}

export function saveToCache<T>(queryKey: string | string[], data: T): void {
  try {
    const key = getCacheKey(queryKey);
    localStorage.setItem(key, JSON.stringify({
      data,
      timestamp: Date.now(),
    }));
  } catch (e) {
    console.warn("Failed to save to cache:", e);
  }
}

export function clearCache(queryKey?: string | string[]): void {
  try {
    if (queryKey) {
      const key = getCacheKey(queryKey);
      localStorage.removeItem(key);
    } else {
      const keysToRemove: string[] = [];
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (key?.startsWith(CACHE_PREFIX)) {
          keysToRemove.push(key);
        }
      }
      keysToRemove.forEach(key => localStorage.removeItem(key));
    }
  } catch (e) {
    console.warn("Failed to clear cache:", e);
  }
}

export function clearGeneratedDataCache(): void {
  const keysToClear = [
    "/api/brd/current",
    "/api/user-stories",
    "/api/test-cases",
    "/api/test-data",
    "/api/copilot-prompts",
  ];
  keysToClear.forEach(key => clearCache(key));
}

export type SessionArtifact = "project" | "documentation" | "analysis" | "featureRequest" | "brd" | "userStories" | "testCases" | "testData" | "bpmn" | "databaseSchema";

export interface WorkflowSession {
  sessionId: string;
  createdAt: number;
  projectName?: string;
  requestType?: string;
  featureTitle?: string;
}

function sessionKey(sessionId: string, artifact: SessionArtifact): string {
  return `${SESSION_PREFIX}${sessionId}_${artifact}`;
}

export function generateSessionId(): string {
  return `sess_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
}

export function createSession(sessionId: string, meta?: Partial<WorkflowSession>): WorkflowSession {
  const session: WorkflowSession = {
    sessionId,
    createdAt: Date.now(),
    ...meta,
  };
  localStorage.setItem(`${SESSION_PREFIX}current`, JSON.stringify(session));
  localStorage.setItem(`${SESSION_PREFIX}session_${sessionId}`, JSON.stringify(session));
  return session;
}

export function getCurrentSession(): WorkflowSession | null {
  try {
    const raw = localStorage.getItem(`${SESSION_PREFIX}current`);
    if (raw) return JSON.parse(raw);
  } catch (e) {
    console.warn("Failed to read current session:", e);
  }
  return null;
}

export function setCurrentSession(sessionId: string): WorkflowSession | null {
  try {
    const raw = localStorage.getItem(`${SESSION_PREFIX}session_${sessionId}`);
    if (raw) {
      localStorage.setItem(`${SESSION_PREFIX}current`, raw);
      return JSON.parse(raw);
    }
  } catch (e) {
    console.warn("Failed to set current session:", e);
  }
  return null;
}

export function saveSessionData<T>(sessionId: string, artifact: SessionArtifact, data: T): void {
  try {
    const key = sessionKey(sessionId, artifact);
    localStorage.setItem(key, JSON.stringify({
      data,
      timestamp: Date.now(),
    }));
  } catch (e) {
    console.warn(`Failed to save session data [${artifact}]:`, e);
  }
}

export function getSessionData<T>(sessionId: string, artifact: SessionArtifact): T | null {
  try {
    const key = sessionKey(sessionId, artifact);
    const raw = localStorage.getItem(key);
    if (raw) {
      const parsed = JSON.parse(raw);
      return parsed.data as T;
    }
  } catch (e) {
    console.warn(`Failed to read session data [${artifact}]:`, e);
  }
  return null;
}

export function clearSessionData(sessionId: string): void {
  try {
    const keysToRemove: string[] = [];
    const prefix = `${SESSION_PREFIX}${sessionId}`;
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key?.startsWith(prefix)) {
        keysToRemove.push(key);
      }
    }
    keysToRemove.forEach(key => localStorage.removeItem(key));
    localStorage.removeItem(`${SESSION_PREFIX}session_${sessionId}`);
  } catch (e) {
    console.warn("Failed to clear session data:", e);
  }
}
