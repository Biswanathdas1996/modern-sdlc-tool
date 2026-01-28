const CACHE_PREFIX = "docugen_cache_";
const CACHE_VERSION = "v1";

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
