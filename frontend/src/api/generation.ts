/** Hooks for Generation Studio and the queue (WP-08: FR-030-FR-043, FR-052). */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api, unwrap, type Schemas } from "./client";

export type GenerationSpec = Schemas["GenerationSpec"];
export type Check = Schemas["GenerationCheckOut"];
export type Queued = Schemas["QueuedOut"];
export type JobRow = Schemas["JobOut"];
export type AssetRow = Schemas["AssetSummary"];
export type VersionRow = Schemas["VersionOut"];
export type JobState = "queued" | "running" | "completed" | "failed" | "cancelled" | "interrupted";

export const SAMPLERS = [
  "euler",
  "euler_ancestral",
  "dpmpp_2m",
  "dpmpp_2m_sde",
  "dpmpp_sde",
  "ddim",
  "uni_pc",
] as const;
export const SCHEDULERS = ["normal", "karras", "exponential", "sgm_uniform", "simple"] as const;
export const VARIANT_COUNTS = [1, 2, 4, 8] as const;
export const ACTIVE: readonly string[] = ["queued", "running"];

export interface JobFilter {
  state?: JobState;
  projectId?: string | null;
  kind?: string;
}

export const generationKeys = {
  project: (id: string) => ["projects", id] as const,
  assets: (projectId: string) => ["assets", projectId] as const,
  versions: (assetId: string) => ["assets", "versions", assetId] as const,
  check: (spec: GenerationSpec | null) => ["generation-check", JSON.stringify(spec)] as const,
  // Under "jobs" so live job events refresh them.
  jobs: (filter: JobFilter) => ["jobs", "list", filter] as const,
  jobSet: (ids: string[]) => ["jobs", "set", ...ids] as const,
};

export const versionFileUrl = (id: string, size: "thumb" | "preview" | "original" = "thumb") =>
  `/api/v1/versions/${id}/file?size=${size}`;

/** The value, once it stopped changing for `ms` (checks run while the user types). */
export function useDebounced<T>(value: T, ms = 400): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), ms);
    return () => clearTimeout(timer);
  }, [value, ms]);
  return settled;
}

export function useProject(projectId: string | null) {
  return useQuery({
    queryKey: generationKeys.project(projectId ?? ""),
    enabled: !!projectId,
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/projects/{project_id}", {
          params: { path: { project_id: projectId ?? "" } },
        }),
      ),
  });
}

export function useAssets(projectId: string | null) {
  return useQuery({
    queryKey: generationKeys.assets(projectId ?? ""),
    enabled: !!projectId,
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/assets", {
          params: { query: { project_id: projectId ?? "", limit: 200 } },
        }),
      ),
  });
}

/** Version states that still change on their own (post-processing, WP-09). */
export const PROCESSING: readonly string[] = ["generated", "processing"];

export function useVersions(assetId: string | null) {
  return useQuery({
    queryKey: generationKeys.versions(assetId ?? ""),
    enabled: !!assetId,
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/assets/{asset_id}/versions", {
          params: { path: { asset_id: assetId ?? "" } },
        }),
      ),
    // Processing runs as jobs after generation; follow it until the version is ready.
    refetchInterval: (q) =>
      (q.state.data ?? []).some((v) => PROCESSING.includes(v.state)) ? 2000 : false,
  });
}

/** Checks before queueing (RULE-015, RULE-007): workflow, models, prompts, problems. */
export function useGenerationCheck(spec: GenerationSpec | null) {
  return useQuery({
    queryKey: generationKeys.check(spec),
    enabled: !!spec,
    queryFn: () => unwrap(api.POST("/api/v1/generations:check", { body: spec as GenerationSpec })),
    // Installed models, licences and the engine change elsewhere; ask again when shown.
    staleTime: 0,
  });
}

function useRefresh() {
  const client = useQueryClient();
  return () => {
    void client.invalidateQueries({ queryKey: ["jobs"] });
    void client.invalidateQueries({ queryKey: ["assets"] });
    void client.invalidateQueries({ queryKey: ["generation-check"] });
  };
}

export function useQueueGeneration() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (spec: GenerationSpec) => unwrap(api.POST("/api/v1/generations", { body: spec })),
    onSettled: refresh,
  });
}

/** FR-052: a new version of the same asset from the stored request, with changes. */
export function useRegenerate() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: ({ versionId, changes }: { versionId: string; changes: Record<string, unknown> }) =>
      unwrap(
        api.POST("/api/v1/versions/{version_id}:regenerate", {
          params: { path: { version_id: versionId } },
          body: changes,
        }),
      ),
    onSettled: refresh,
  });
}

/** FR-065: process a generated version, or retry failed processing (T-04R). */
export function useProcessVersion() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (versionId: string) =>
      unwrap(
        api.POST("/api/v1/versions/{version_id}:process", {
          params: { path: { version_id: versionId } },
        }),
      ),
    onSettled: refresh,
  });
}

export function useJobs(filter: JobFilter) {
  return useQuery({
    queryKey: generationKeys.jobs(filter),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/jobs", {
          params: {
            query: {
              ...(filter.state ? { state: filter.state } : {}),
              ...(filter.projectId ? { project_id: filter.projectId } : {}),
              ...(filter.kind ? { kind: filter.kind } : {}),
              limit: 200,
            },
          },
        }),
      ),
    // SSE events refresh it; the interval only covers a lost event stream.
    refetchInterval: (query) =>
      (query.state.data ?? []).some((j) => ACTIVE.includes(j.state)) ? 3000 : 15_000,
  });
}

/** The jobs queued from this screen, refreshed while any is still active. */
export function useJobSet(ids: string[]) {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: generationKeys.jobSet(ids),
    enabled: ids.length > 0,
    queryFn: () =>
      Promise.all(
        ids.map((id) =>
          unwrap(api.GET("/api/v1/jobs/{job_id}", { params: { path: { job_id: id } } })),
        ),
      ),
    refetchInterval: (q) =>
      (q.state.data ?? []).some((j) => ACTIVE.includes(j.state)) ? 1500 : false,
  });
  // A finished job added versions: show them.
  const finished = (query.data ?? []).filter((j) => j.state === "completed").length;
  useEffect(() => {
    if (finished) void client.invalidateQueries({ queryKey: ["assets"] });
  }, [client, finished]);
  return query;
}

export function useJobAction() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: ({ jobId, action }: { jobId: string; action: "cancel" | "retry" }) =>
      action === "cancel"
        ? unwrap(api.POST("/api/v1/jobs/{job_id}/cancel", { params: { path: { job_id: jobId } } }))
        : unwrap(api.POST("/api/v1/jobs/{job_id}/retry", { params: { path: { job_id: jobId } } })),
    onSettled: refresh,
  });
}

/** Engine step progress of a generation job (from ComfyUI `/ws`), or null. */
export function stepProgress(job: JobRow): { step: number; of: number } | null {
  const p = job.progress as { step?: number | null; of?: number | null };
  return p.step != null && p.of ? { step: p.step, of: p.of } : null;
}

/** What a generation or processing job works on, from its stored plan or params. */
export function generationInfo(job: JobRow): {
  assetId: string | null;
  seed: number | null;
  workflow: string | null;
} {
  const params = job.params as { plan?: Record<string, unknown>; asset_id?: unknown };
  const plan = params.plan ?? {};
  const workflow = plan.workflow as { id?: string; version?: number } | undefined;
  const assetId = plan.asset_id ?? params.asset_id;
  return {
    assetId: typeof assetId === "string" ? assetId : null,
    seed: typeof plan.seed === "number" ? plan.seed : null,
    workflow: workflow?.id ? `${workflow.id} v${workflow.version ?? 1}` : null,
  };
}

/** A random seed in the range the engine accepts. */
export function randomSeed(): number {
  return Math.floor(Math.random() * 2 ** 32);
}
