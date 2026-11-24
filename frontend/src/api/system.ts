/** Hooks for the dashboard, settings, system status, backups and the audit log
 * (WP-16: FR-100, FR-110-FR-112, FR-115). */
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap, type Schemas } from "./client";

export type SystemStatus = Schemas["StatusOut"];
export type AppSettings = Schemas["SettingsOut"];
export type Backup = Schemas["BackupOut"];
export type Dashboard = Schemas["DashboardOut"];
export type AuditEntry = Schemas["AuditOut"];

export const ACTORS = ["user", "mcp", "system"] as const;
export const AUDIT_PAGE = 50;

export const systemKeys = {
  status: ["system", "status"] as const,
  settings: ["settings"] as const,
  backups: ["backups"] as const,
  dashboard: (projectId: string) => ["assets", "dashboard", projectId] as const,
  audit: (filter: AuditFilter) => ["audit", "log", filter] as const,
  actions: (projectId: string | null) => ["audit", "actions", projectId] as const,
};

export function useSystemStatus() {
  return useQuery({
    queryKey: systemKeys.status,
    queryFn: () => unwrap(api.GET("/api/v1/system/status")),
    refetchInterval: 15_000,
  });
}

export function useAppSettings() {
  return useQuery({
    queryKey: systemKeys.settings,
    queryFn: () => unwrap(api.GET("/api/v1/settings")),
  });
}

export function useUpdateSettings() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<AppSettings>) => unwrap(api.PATCH("/api/v1/settings", { body })),
    onSuccess: (data) => {
      client.setQueryData(systemKeys.settings, data);
      void client.invalidateQueries({ queryKey: ["system"] });
      void client.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
}

export function useBackups() {
  return useQuery({
    queryKey: systemKeys.backups,
    queryFn: () => unwrap(api.GET("/api/v1/backups")),
  });
}

/** A fresh key per click: a retried request never queues a second job. */
function idempotencyKey(): string {
  return `ui-${crypto.randomUUID()}`;
}

export function useCreateBackup() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/backups", {
          params: { header: { "Idempotency-Key": idempotencyKey() } },
        }),
      ),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["jobs"] }),
  });
}

export function useRestoreBackup() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (name: string) =>
      unwrap(
        api.POST("/api/v1/backups:restore", {
          body: { name },
          params: { header: { "Idempotency-Key": idempotencyKey() } },
        }),
      ),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["jobs"] }),
  });
}

export function useDashboard(projectId: string) {
  return useQuery({
    queryKey: systemKeys.dashboard(projectId),
    queryFn: () =>
      unwrap(api.GET("/api/v1/dashboard", { params: { query: { project_id: projectId } } })),
    enabled: !!projectId,
    refetchInterval: 30_000,
  });
}

export interface AuditFilter {
  projectId: string | null;
  actor: string | null;
  action: string | null;
}

/** The audit log, newest first, a page at a time (FR-115). */
export function useAuditLog(filter: AuditFilter) {
  return useInfiniteQuery({
    queryKey: systemKeys.audit(filter),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET("/api/v1/audit", {
          params: {
            query: {
              ...(filter.projectId ? { project_id: filter.projectId } : {}),
              ...(filter.actor ? { actor: filter.actor } : {}),
              ...(filter.action ? { action: filter.action } : {}),
              ...(pageParam ? { before: pageParam } : {}),
              limit: AUDIT_PAGE,
            },
          },
        }),
      ),
    getNextPageParam: (last) => (last.length === AUDIT_PAGE ? last[last.length - 1]?.id : null),
  });
}

export function useAuditActions(projectId: string | null) {
  return useQuery({
    queryKey: systemKeys.actions(projectId),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/audit/actions", {
          params: { query: projectId ? { project_id: projectId } : {} },
        }),
      ),
  });
}

export function formatBytes(n: number | null | undefined, language: string): string {
  if (n == null) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = n;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const digits = unit === 0 || value >= 100 ? 0 : 1;
  return `${new Intl.NumberFormat(language, { maximumFractionDigits: digits }).format(value)} ${units[unit]}`;
}
