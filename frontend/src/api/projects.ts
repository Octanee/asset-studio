/** Hooks for the Projects screen, new project and project settings (WP-16 part 2:
 * FR-001-FR-008, RULE-005, RULE-010). */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useDebounced } from "./generation";
import { api, unwrap, type Schemas } from "./client";

export type Project = Schemas["ProjectOut"];
export type ProjectDetail = Schemas["ProjectDetail"];
export type ProjectConfig = Schemas["ProjectConfig"];
export type ConfigVersion = Schemas["ConfigVersionOut"];
export type Draft = Schemas["DraftOut"];
export type Problem = { loc?: (string | number)[]; msg?: string; type?: string };

export const EMPTY_CONFIG = {
  name: "",
  description: "",
  type: "illustration",
  languages: ["pl"],
  intended_use: "commercial",
  categories: [] as { slug: string; name: string }[],
  naming: "{asset}-{view}",
} as const;

export const projectKeys = {
  all: (archived: boolean) => ["projects", "list", { archived }] as const,
  counts: ["assets", "project-counts"] as const,
  drafts: ["projects", "drafts"] as const,
  draft: (id: string) => ["projects", "drafts", id] as const,
  versions: (id: string) => ["projects", id, "versions"] as const,
};

export function useProjectList(includeArchived: boolean) {
  return useQuery({
    queryKey: projectKeys.all(includeArchived),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/projects", { params: { query: { include_archived: includeArchived } } }),
      ),
  });
}

export function useProjectCounts() {
  return useQuery({
    queryKey: projectKeys.counts,
    queryFn: () => unwrap(api.GET("/api/v1/dashboard/projects")),
    select: (rows) => new Map(rows.map((r) => [r.project_id, r])),
  });
}

export function useDrafts() {
  return useQuery({
    queryKey: projectKeys.drafts,
    queryFn: () => unwrap(api.GET("/api/v1/projects/drafts")),
  });
}

export function useDraft(id: string | null) {
  return useQuery({
    queryKey: projectKeys.draft(id ?? ""),
    enabled: !!id,
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/projects/drafts/{draft_id}", {
          params: { path: { draft_id: id ?? "" } },
        }),
      ),
  });
}

export function useConfigVersions(projectId: string) {
  return useQuery({
    queryKey: projectKeys.versions(projectId),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/projects/{project_id}/config/versions", {
          params: { path: { project_id: projectId } },
        }),
      ),
  });
}

/** Live schema check of a configuration being edited (nothing is saved). */
export function useConfigCheck(config: unknown) {
  const debounced = useDebounced(config, 400);
  return useQuery({
    queryKey: ["projects", "check", debounced],
    queryFn: () =>
      unwrap(
        api.POST("/api/v1/projects:validate", {
          body: { config: debounced as Record<string, unknown> },
        }),
      ),
    placeholderData: (previous) => previous,
  });
}

function useInvalidate() {
  const client = useQueryClient();
  return () => void client.invalidateQueries({ queryKey: ["projects"] });
}

export function useCreateProject() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (config: ProjectConfig) => unwrap(api.POST("/api/v1/projects", { body: config })),
    onSuccess: invalidate,
  });
}

export function useConfirmDraft() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, config }: { id: string; config: ProjectConfig }) =>
      unwrap(
        api.POST("/api/v1/projects/drafts/{draft_id}/confirm", {
          params: { path: { draft_id: id } },
          body: { config },
        }),
      ),
    onSuccess: invalidate,
  });
}

export function useDiscardDraft() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(
        api.POST("/api/v1/projects/drafts/{draft_id}/discard", {
          params: { path: { draft_id: id } },
        }),
      ),
    onSuccess: invalidate,
  });
}

export function useImportProject() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (document: Record<string, unknown>) =>
      unwrap(api.POST("/api/v1/projects/import", { body: document })),
    onSuccess: invalidate,
  });
}

export function useUpdateConfig(projectId: string) {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: { config: ProjectConfig; acknowledge_breaking: boolean; note: string }) =>
      unwrap(
        api.PUT("/api/v1/projects/{project_id}/config", {
          params: { path: { project_id: projectId } },
          body,
        }),
      ),
    onSuccess: invalidate,
  });
}

export function useProjectAction() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: async (
      a:
        | { kind: "archive"; id: string }
        | { kind: "restore"; id: string }
        | { kind: "clone"; id: string; name: string }
        | { kind: "mcp"; id: string; allow: boolean },
    ): Promise<unknown> => {
      const path = { params: { path: { project_id: a.id } } };
      if (a.kind === "archive" || a.kind === "restore") {
        return a.kind === "archive"
          ? unwrap(api.POST("/api/v1/projects/{project_id}/archive", path))
          : unwrap(api.POST("/api/v1/projects/{project_id}/restore", path));
      }
      if (a.kind === "clone")
        return unwrap(
          api.POST("/api/v1/projects/{project_id}/clone", { ...path, body: { name: a.name } }),
        );
      return unwrap(
        api.PATCH("/api/v1/projects/{project_id}/settings", {
          ...path,
          body: { mcp_can_decide: a.allow },
        }),
      );
    },
    onSuccess: invalidate,
  });
}

/** Download the project's configuration as JSON (FR-005). */
export async function exportConfig(project: { id: string; slug: string }): Promise<void> {
  const document = await unwrap(
    api.GET("/api/v1/projects/{project_id}/config/export", {
      params: { path: { project_id: project.id } },
    }),
  );
  const blob = new Blob([JSON.stringify(document, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = window.document.createElement("a");
  a.href = url;
  a.download = `${project.slug}.asset-studio.json`;
  a.click();
  URL.revokeObjectURL(url);
}

/** Problems from the schema check, as "field: message" lines. */
export function problemLines(problems: readonly Problem[] | undefined): string[] {
  return (problems ?? []).map((p) => {
    const where = (p.loc ?? []).filter((x) => x !== "body").join(".");
    return where ? `${where}: ${p.msg ?? ""}` : (p.msg ?? "");
  });
}
