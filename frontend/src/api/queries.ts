import { QueryClient, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import { ApiError, api, unwrap } from "./client";

export const queryKeys = {
  session: ["session"] as const,
  health: ["system", "health"] as const,
  projects: ["projects"] as const,
  queueSummary: ["jobs", "summary"] as const,
};

export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 10_000,
        refetchOnWindowFocus: false,
        // Problems are answers, not glitches: only retry network-level failures.
        retry: (count, error) => !(error instanceof ApiError && error.status > 0) && count < 2,
      },
    },
  });
}

/** Starts the browser session (sets the session cookie) before anything else is asked. */
export function useSession() {
  return useQuery({
    queryKey: queryKeys.session,
    queryFn: () => unwrap(api.GET("/api/v1/session")),
    staleTime: Infinity,
    retry: false,
  });
}

export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: () => unwrap(api.GET("/api/v1/system/health")),
    refetchInterval: 30_000,
  });
}

export function useProjects() {
  return useQuery({
    queryKey: queryKeys.projects,
    queryFn: () => unwrap(api.GET("/api/v1/projects")),
  });
}

export interface QueueCounts {
  running: number;
  queued: number;
  failed: number;
  workers: number;
  waitReason: string | null;
}

export function useQueueCounts() {
  return useQuery({
    queryKey: queryKeys.queueSummary,
    queryFn: () => unwrap(api.GET("/api/v1/jobs/summary")),
    refetchInterval: 15_000,
    select: (summary): QueueCounts => {
      const lanes = Object.values(summary.lanes);
      const sum = (state: string) => lanes.reduce((n, lane) => n + (lane[state] ?? 0), 0);
      return {
        running: sum("running"),
        queued: sum("queued"),
        failed: sum("failed") + sum("interrupted"),
        workers: summary.workers.length,
        waitReason: Object.values(summary.wait_reasons)[0] ?? null,
      };
    },
  });
}

/** Live job events over SSE (FR-041, NFR-003). The browser reconnects with Last-Event-ID by
 * itself; each event refreshes the job queries, so screens never poll faster than needed. */
export function useLiveEvents(enabled: boolean): void {
  const client = useQueryClient();
  useEffect(() => {
    if (!enabled || typeof EventSource === "undefined") return;
    const source = new EventSource("/api/v1/events");
    const refresh = () => void client.invalidateQueries({ queryKey: ["jobs"] });
    source.addEventListener("job", refresh);
    return () => {
      source.removeEventListener("job", refresh);
      source.close();
    };
  }, [client, enabled]);
}
