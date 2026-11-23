/** Hooks for the library, asset details, review and compare screens (WP-10: FR-049-FR-064). */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap, unwrapEmpty, type Schemas } from "./client";

export type AssetSummary = Schemas["AssetSummary"];
export type AssetDetail = Schemas["AssetDetail"];
export type Version = Schemas["VersionOut"];
export type VersionDetail = Schemas["VersionDetail"];
export type QueueVersion = Schemas["QueueVersionOut"];
export type Collection = Schemas["CollectionOut"];
export type Comment = Schemas["CommentOut"];
export type Duplicate = Schemas["DuplicateOut"];
export type Validation = Schemas["ValidationOut"];
export type AuditEntry = Schemas["AuditOut"];
export type Sort = "newest" | "oldest" | "name" | "updated";
export type ClientAction = Schemas["TransitionRequest"]["action"];

export const STATES = [
  "generated",
  "processing",
  "processing_failed",
  "awaiting_review",
  "approved",
  "rejected",
  "published",
  "archived",
] as const;
export type VersionState = (typeof STATES)[number];
export const SORTS: readonly Sort[] = ["newest", "oldest", "name", "updated"];
export const PAGE = 60;

export interface LibraryFilter {
  projectId: string;
  q?: string;
  category?: string;
  state?: VersionState;
  styleId?: string;
  characterId?: string;
  collectionId?: string;
  tag?: string;
  favorite?: boolean;
  includeArchived?: boolean;
  sort: Sort;
  offset?: number;
}

export const reviewKeys = {
  // Under "assets" so generation and processing refresh them too.
  library: (f: LibraryFilter) => ["assets", "library", f] as const,
  asset: (id: string) => ["assets", "detail", id] as const,
  queue: (projectId: string) => ["assets", "review-queue", projectId] as const,
  version: (id: string) => ["assets", "version", id] as const,
  validation: (id: string) => ["assets", "validation", id] as const,
  duplicates: (id: string) => ["assets", "duplicates", id] as const,
  comments: (id: string) => ["comments", id] as const,
  collections: (projectId: string) => ["collections", projectId] as const,
  tags: (projectId: string, prefix: string) => ["tags", projectId, prefix] as const,
  trail: (ids: string[]) => ["audit", "trail", ...ids] as const,
};

export const fileUrl = (
  id: string,
  size: "thumb" | "preview" | "processed" | "original" = "preview",
  download = false,
) => `/api/v1/versions/${id}/file?size=${size}${download ? "&download=true" : ""}`;

/** The version the library shows for an asset: the published one, else the newest. */
export function shownVersion<V extends { state: string }>(versions: V[]): V | undefined {
  return (
    versions.find((v) => v.state === "published") ?? versions.find((v) => v.state !== "deleted")
  );
}

export function useLibrary(filter: LibraryFilter) {
  return useQuery({
    queryKey: reviewKeys.library(filter),
    placeholderData: keepPreviousData,
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/assets", {
          params: {
            query: {
              project_id: filter.projectId,
              sort: filter.sort,
              limit: PAGE,
              offset: filter.offset ?? 0,
              ...(filter.q ? { q: filter.q } : {}),
              ...(filter.category ? { category: filter.category } : {}),
              ...(filter.state ? { state: filter.state } : {}),
              ...(filter.styleId ? { style_id: filter.styleId } : {}),
              ...(filter.characterId ? { character_id: filter.characterId } : {}),
              ...(filter.collectionId ? { collection_id: filter.collectionId } : {}),
              ...(filter.tag ? { tag: filter.tag } : {}),
              ...(filter.favorite ? { favorite: true } : {}),
              ...(filter.includeArchived ? { include_archived: true } : {}),
            },
          },
        }),
      ),
  });
}

export function useAssetDetail(assetId: string | null) {
  return useQuery({
    queryKey: reviewKeys.asset(assetId ?? ""),
    enabled: !!assetId,
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/assets/{asset_id}", { params: { path: { asset_id: assetId ?? "" } } }),
      ),
  });
}

export function useVersionDetail(versionId: string | null) {
  return useQuery({
    queryKey: reviewKeys.version(versionId ?? ""),
    enabled: !!versionId,
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/versions/{version_id}", {
          params: { path: { version_id: versionId ?? "" } },
        }),
      ),
  });
}

/** Versions waiting for a decision, oldest first (FR-061). */
export function useReviewQueue(projectId: string) {
  return useQuery({
    queryKey: reviewKeys.queue(projectId),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/versions", {
          params: { query: { project_id: projectId, state: "awaiting_review", limit: 200 } },
        }),
      ),
    refetchInterval: 15_000,
  });
}

export function useValidation(versionId: string | null) {
  return useQuery({
    queryKey: reviewKeys.validation(versionId ?? ""),
    enabled: !!versionId,
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/versions/{version_id}/validation", {
          params: { path: { version_id: versionId ?? "" } },
        }),
      ),
  });
}

export function useDuplicates(versionId: string | null) {
  return useQuery({
    queryKey: reviewKeys.duplicates(versionId ?? ""),
    enabled: !!versionId,
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/versions/{version_id}/duplicates", {
          params: { path: { version_id: versionId ?? "" } },
        }),
      ),
  });
}

export function useComments(versionId: string | null) {
  return useQuery({
    queryKey: reviewKeys.comments(versionId ?? ""),
    enabled: !!versionId,
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/versions/{version_id}/comments", {
          params: { path: { version_id: versionId ?? "" } },
        }),
      ),
    // Claude may comment over MCP while the screen is open.
    refetchInterval: 20_000,
  });
}

export function useAddComment(versionId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: string) =>
      unwrap(
        api.POST("/api/v1/versions/{version_id}/comments", {
          params: { path: { version_id: versionId } },
          body: { body },
        }),
      ),
    onSuccess: () => void client.invalidateQueries({ queryKey: reviewKeys.comments(versionId) }),
  });
}

function useAssetsRefresh() {
  const client = useQueryClient();
  return () => {
    void client.invalidateQueries({ queryKey: ["assets"] });
    void client.invalidateQueries({ queryKey: ["audit"] });
    void client.invalidateQueries({ queryKey: ["collections"] });
    void client.invalidateQueries({ queryKey: ["tags"] });
  };
}

/** A lifecycle action from the UI (FR-053, FR-061-FR-063). */
export function useTransition() {
  const refresh = useAssetsRefresh();
  return useMutation({
    mutationFn: ({
      versionId,
      action,
      reason = "",
    }: {
      versionId: string;
      action: ClientAction;
      reason?: string;
    }) =>
      unwrap(
        api.POST("/api/v1/versions/{version_id}/transitions", {
          params: { path: { version_id: versionId } },
          body: { action, reason },
        }),
      ),
    onSettled: refresh,
  });
}

/** FR-054: permanent deletion; the API needs the version id back as confirmation. */
export function useDeleteVersion() {
  const refresh = useAssetsRefresh();
  return useMutation({
    mutationFn: (versionId: string) =>
      unwrap(
        api.DELETE("/api/v1/versions/{version_id}", {
          params: { path: { version_id: versionId }, query: { confirm: versionId } },
        }),
      ),
    onSettled: refresh,
  });
}

export function useUpdateAsset() {
  const refresh = useAssetsRefresh();
  return useMutation({
    mutationFn: ({
      assetId,
      ...body
    }: {
      assetId: string;
      name?: string;
      tags?: string[];
      favorite?: boolean;
    }) =>
      unwrap(
        api.PATCH("/api/v1/assets/{asset_id}", { params: { path: { asset_id: assetId } }, body }),
      ),
    onSettled: refresh,
  });
}

export function useArchiveAssets() {
  const refresh = useAssetsRefresh();
  return useMutation({
    mutationFn: async ({ ids, archived }: { ids: string[]; archived: boolean }) => {
      for (const id of ids) {
        const params = { params: { path: { asset_id: id } } };
        await unwrap(
          archived
            ? api.POST("/api/v1/assets/{asset_id}/archive", params)
            : api.POST("/api/v1/assets/{asset_id}/restore", params),
        );
      }
    },
    onSettled: refresh,
  });
}

export function useTags(projectId: string, prefix = "") {
  return useQuery({
    queryKey: reviewKeys.tags(projectId, prefix),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/assets/tags", {
          params: { query: { project_id: projectId, prefix, limit: 30 } },
        }),
      ),
    staleTime: 30_000,
  });
}

export function useCollections(projectId: string) {
  return useQuery({
    queryKey: reviewKeys.collections(projectId),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/projects/{project_id}/collections", {
          params: { path: { project_id: projectId } },
        }),
      ),
  });
}

export function useCollectionActions(projectId: string) {
  const refresh = useAssetsRefresh();
  const create = useMutation({
    mutationFn: (name: string) =>
      unwrap(
        api.POST("/api/v1/projects/{project_id}/collections", {
          params: { path: { project_id: projectId } },
          body: { name },
        }),
      ),
    onSettled: refresh,
  });
  const add = useMutation({
    mutationFn: ({ collectionId, assetIds }: { collectionId: string; assetIds: string[] }) =>
      unwrap(
        api.POST("/api/v1/collections/{collection_id}/assets", {
          params: { path: { collection_id: collectionId } },
          body: { asset_ids: assetIds },
        }),
      ),
    onSettled: refresh,
  });
  const remove = useMutation({
    mutationFn: ({ collectionId, assetId }: { collectionId: string; assetId: string }) =>
      unwrap(
        api.DELETE("/api/v1/collections/{collection_id}/assets/{asset_id}", {
          params: { path: { collection_id: collectionId, asset_id: assetId } },
        }),
      ),
    onSettled: refresh,
  });
  const drop = useMutation({
    mutationFn: (collectionId: string) =>
      unwrapEmpty(
        api.DELETE("/api/v1/collections/{collection_id}", {
          params: { path: { collection_id: collectionId } },
        }),
      ),
    onSettled: refresh,
  });
  return { create, add, remove, drop };
}

/** An asset's audit trail: the asset and each of its versions (FR-051). */
export function useAuditTrail(ids: string[]) {
  return useQuery({
    queryKey: reviewKeys.trail(ids),
    enabled: ids.length > 0,
    queryFn: () =>
      unwrap(api.GET("/api/v1/audit", { params: { query: { subject_id: ids, limit: 100 } } })),
  });
}

/** Flat `path → value` pairs of generation metadata, for the parameter diff (FR-058). */
export function flatten(
  value: unknown,
  prefix = "",
  out: Record<string, string> = {},
): Record<string, string> {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      flatten(v, prefix ? `${prefix}.${k}` : k, out);
    }
  } else if (prefix) {
    out[prefix] =
      value == null ? "—" : Array.isArray(value) ? JSON.stringify(value) : String(value);
  }
  return out;
}

export function metadataDiff(a: unknown, b: unknown) {
  const fa = flatten(a);
  const fb = flatten(b);
  const keys = [...new Set([...Object.keys(fa), ...Object.keys(fb)])].sort();
  return keys.map((key) => {
    const left = fa[key] ?? "—";
    const right = fb[key] ?? "—";
    return { key, a: left, b: right, same: left === right };
  });
}
