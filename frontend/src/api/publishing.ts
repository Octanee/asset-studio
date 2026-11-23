/** Hooks for export presets, targets and publishing (WP-11: FR-090-FR-095, RULE-004). */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap, type Schemas } from "./client";

export type Preset = Schemas["PresetOut"];
export type PresetDefinition = Schemas["PresetDefinition"];
export type Size = Schemas["Size"];
export type Target = Schemas["TargetOut"];
export type ExportRoot = Schemas["ExportRootOut"];
export type Plan = Schemas["PlanOut"];
export type Publication = Schemas["PublicationOut"];

export const FORMATS = ["webp", "png", "jpeg"] as const;
export const NEW_PRESET: PresetDefinition = {
  format: "webp",
  sizes: [{ suffix: "", width: 1024, height: 1024 }],
  naming: "{asset}-{view}{suffix}",
  folders: "",
  background: "keep",
  resize: "contain",
  optimize: true,
  quality: 90,
  metadata: "none",
};

/** What to publish (FR-092). */
export type Source =
  | { kind: "versions"; versionIds: string[] }
  | { kind: "collection"; collectionId: string }
  | { kind: "project" };

export const publishingKeys = {
  roots: ["export-roots"] as const,
  presets: (projectId: string) => ["presets", projectId] as const,
  targets: (projectId: string) => ["targets", projectId] as const,
  // Under "assets" so publishing refreshes the asset screens.
  publications: (filter: Record<string, string>) => ["assets", "publications", filter] as const,
};

export function useExportRoots() {
  return useQuery({
    queryKey: publishingKeys.roots,
    queryFn: () => unwrap(api.GET("/api/v1/export-roots")),
    staleTime: 60_000,
  });
}

export function usePresets(projectId: string) {
  return useQuery({
    queryKey: publishingKeys.presets(projectId),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/projects/{project_id}/presets", {
          params: { path: { project_id: projectId } },
        }),
      ),
  });
}

export function useTargets(projectId: string) {
  return useQuery({
    queryKey: publishingKeys.targets(projectId),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/projects/{project_id}/targets", {
          params: { path: { project_id: projectId } },
        }),
      ),
  });
}

export function useSavePreset(projectId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      name,
      definition,
    }: {
      id?: string;
      name: string;
      definition: PresetDefinition;
    }) =>
      id
        ? unwrap(
            api.PUT("/api/v1/presets/{preset_id}", {
              params: { path: { preset_id: id } },
              body: { name, definition },
            }),
          )
        : unwrap(
            api.POST("/api/v1/projects/{project_id}/presets", {
              params: { path: { project_id: projectId } },
              body: { name, definition },
            }),
          ),
    onSuccess: () => void client.invalidateQueries({ queryKey: publishingKeys.presets(projectId) }),
  });
}

export function useCreateTarget(projectId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; root_id: string; subdir: string }) =>
      unwrap(
        api.POST("/api/v1/projects/{project_id}/targets", {
          params: { path: { project_id: projectId } },
          body,
        }),
      ),
    onSuccess: () => void client.invalidateQueries({ queryKey: publishingKeys.targets(projectId) }),
  });
}

export function usePlan() {
  return useMutation({
    mutationFn: ({
      projectId,
      presetId,
      targetId,
      source,
    }: {
      projectId: string;
      presetId: string;
      targetId: string;
      source: Source;
    }) =>
      unwrap(
        api.POST("/api/v1/publications:plan", {
          body: {
            project_id: projectId,
            preset_id: presetId,
            target_id: targetId,
            ...(source.kind === "versions" ? { version_ids: source.versionIds } : {}),
            ...(source.kind === "collection" ? { collection_id: source.collectionId } : {}),
            whole_project: source.kind === "project",
          },
        }),
      ),
  });
}

/** RULE-004: the overwrites the user confirmed, each by its path. */
export function usePublish() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ planId, confirm }: { planId: string; confirm: string[] }) =>
      unwrap(
        api.POST("/api/v1/publications", {
          body: { plan_id: planId, confirm_overwrites: confirm },
        }),
      ),
    onSettled: () => void client.invalidateQueries({ queryKey: ["jobs"] }),
  });
}

export function usePublications(filter: { projectId?: string; assetId?: string }) {
  const query: Record<string, string> = {};
  if (filter.projectId) query.project_id = filter.projectId;
  if (filter.assetId) query.asset_id = filter.assetId;
  return useQuery({
    queryKey: publishingKeys.publications(query),
    queryFn: () =>
      unwrap(api.GET("/api/v1/publications", { params: { query: { ...query, limit: 30 } } })),
  });
}

/** Versions that can be published: approved, or published and published again (FR-092). */
export function usePublishable(projectId: string) {
  return useQuery({
    queryKey: ["assets", "publishable", projectId],
    queryFn: async () => {
      const [approved, published] = await Promise.all(
        (["approved", "published"] as const).map((state) =>
          unwrap(
            api.GET("/api/v1/versions", {
              params: { query: { project_id: projectId, state, limit: 200 } },
            }),
          ),
        ),
      );
      return [...(approved ?? []), ...(published ?? [])].sort((a, b) =>
        a.asset.name.localeCompare(b.asset.name),
      );
    },
  });
}
