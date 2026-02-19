import { QueryClient, QueryFunction } from "@tanstack/react-query";
import { getFromCache, saveToCache, clearCache } from "./localStorageCache";

export { clearCache } from "./localStorageCache";

async function throwIfResNotOk(res: Response) {
  if (!res.ok) {
    const text = (await res.text()) || res.statusText;
    throw new Error(`${res.status}: ${text}`);
  }
}

export async function apiRequest(
  method: string,
  url: string,
  data?: unknown | undefined,
): Promise<Response> {
  const res = await fetch(url, {
    method,
    headers: data ? { "Content-Type": "application/json" } : {},
    body: data ? JSON.stringify(data) : undefined,
    credentials: "include",
  });

  await throwIfResNotOk(res);
  return res;
}

type UnauthorizedBehavior = "returnNull" | "throw";

const CACHEABLE_ENDPOINTS = [
  "/api/projects",
  "/api/documentation/current",
  "/api/analysis/current",
  "/api/brd/current",
  "/api/bpmn/current",
  "/api/database-schema/current",
  "/api/requirements/current",
  "/api/user-stories",
  "/api/test-cases",
  "/api/test-data",
  "/api/copilot-prompts",
];

function isCacheableEndpoint(url: string): boolean {
  return CACHEABLE_ENDPOINTS.some(endpoint => url.startsWith(endpoint));
}

export const getQueryFn: <T>(options: {
  on401: UnauthorizedBehavior;
}) => QueryFunction<T> =
  ({ on401: unauthorizedBehavior }) =>
  async ({ queryKey }) => {
    const url = queryKey.join("/") as string;
    
    try {
      const res = await fetch(url, {
        credentials: "include",
      });

      if (unauthorizedBehavior === "returnNull" && res.status === 401) {
        return null;
      }

      await throwIfResNotOk(res);
      const data = await res.json();
      
      if (isCacheableEndpoint(url)) {
        saveToCache(url, data);
      }
      
      return data;
    } catch (error) {
      if (isCacheableEndpoint(url)) {
        const cached = getFromCache<T>(url);
        if (cached !== null) {
          return cached;
        }
      }
      throw error;
    }
  };

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      queryFn: getQueryFn({ on401: "throw" }),
      refetchInterval: false,
      refetchOnWindowFocus: false,
      staleTime: Infinity,
      retry: false,
    },
    mutations: {
      retry: false,
    },
  },
});

export function hydrateFromLocalStorage(): void {
  CACHEABLE_ENDPOINTS.forEach(endpoint => {
    const cached = getFromCache(endpoint);
    if (cached !== null) {
      queryClient.setQueryData([endpoint], cached);
    }
  });
}
