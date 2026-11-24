/** Hooks for LoRA training (WP-13: FR-070-FR-075, RULE-016, RULE-017). */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap, type Schemas } from "./client";
import { useDebounced } from "./generation";

export type Dataset = Schemas["DatasetOut"];
export type TrainingItem = Schemas["ItemOut"];
export type TrainingRun = Schemas["RunOut"];
export type Estimate = Schemas["EstimateOut"];
export type Family = "sd15" | "sdxl";
export interface RunDraft {
  dataset_id: string;
  family: Family;
  base_model_id: string;
  steps?: number | null;
}

/** The presets' defaults (ADR-011); the screen changes only family, base model and steps. */
const DEFAULTS = {
  network_dim: 16,
  network_alpha: 8,
  learning_rate: 1e-4,
  seed: 42,
  acknowledged_estimate: false,
};

export const trainingKeys = {
  datasets: (projectId: string) => ["training", "datasets", projectId] as const,
  items: (datasetId: string) => ["training", "items", datasetId] as const,
  // Under "jobs" so live job events refresh the runs and their progress.
  runs: (projectId: string) => ["jobs", "training-runs", projectId] as const,
};

export const itemFileUrl = (id: string) => `/api/v1/training-items/${id}/file`;

export function useDatasets(projectId: string) {
  return useQuery({
    queryKey: trainingKeys.datasets(projectId),
    enabled: !!projectId,
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/projects/{project_id}/datasets", {
          params: { path: { project_id: projectId } },
        }),
      ),
  });
}

export function useItems(datasetId: string | null) {
  return useQuery({
    queryKey: trainingKeys.items(datasetId ?? ""),
    enabled: !!datasetId,
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/datasets/{dataset_id}/items", {
          params: { path: { dataset_id: datasetId ?? "" } },
        }),
      ),
  });
}

export function useRuns(projectId: string) {
  return useQuery({
    queryKey: trainingKeys.runs(projectId),
    enabled: !!projectId,
    queryFn: () =>
      unwrap(api.GET("/api/v1/training-runs", { params: { query: { project_id: projectId } } })),
    refetchInterval: (q) =>
      (q.state.data ?? []).some((r) => r.job && ["queued", "running"].includes(r.job.state))
        ? 3000
        : false,
  });
}

/** The estimate for the run being set up (RULE-016); nothing is started. */
export function useEstimate(draft: RunDraft | null) {
  const debounced = useDebounced(draft, 300);
  return useQuery({
    queryKey: ["training", "estimate", debounced],
    enabled: !!debounced?.dataset_id && !!debounced.base_model_id,
    queryFn: () =>
      unwrap(
        api.POST("/api/v1/training-runs:estimate", {
          body: { ...DEFAULTS, ...(debounced as RunDraft) },
        }),
      ),
    placeholderData: keepPreviousData,
    retry: false,
  });
}

function useRefresh() {
  const client = useQueryClient();
  return () => {
    void client.invalidateQueries({ queryKey: ["training"] });
    void client.invalidateQueries({ queryKey: ["jobs"] });
  };
}

export function useCreateDataset(projectId: string) {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (body: { name: string; trigger_word: string }) =>
      unwrap(
        api.POST("/api/v1/projects/{project_id}/datasets", {
          params: { path: { project_id: projectId } },
          body,
        }),
      ),
    onSuccess: refresh,
  });
}

export function useDatasetActions(datasetId: string) {
  const refresh = useRefresh();
  const addVersions = useMutation({
    mutationFn: (versionIds: string[]) =>
      unwrap(
        api.POST("/api/v1/datasets/{dataset_id}/items:versions", {
          params: { path: { dataset_id: datasetId } },
          body: { version_ids: versionIds },
        }),
      ),
    onSuccess: refresh,
  });
  const upload = useMutation({
    mutationFn: async (files: File[]) => {
      // The body is the image itself; the server checks the bytes (FR-025).
      for (const file of files) {
        await unwrap(
          api.POST("/api/v1/datasets/{dataset_id}/items", {
            params: { path: { dataset_id: datasetId }, query: { caption: "" } },
            body: file as unknown as string,
            bodySerializer: (body: unknown) => body as BodyInit,
            headers: { "Content-Type": file.type || "application/octet-stream" },
          }),
        );
      }
    },
    onSettled: refresh,
  });
  const caption = useMutation({
    mutationFn: ({ id, text }: { id: string; text: string }) =>
      unwrap(
        api.PATCH("/api/v1/training-items/{item_id}", {
          params: { path: { item_id: id } },
          body: { caption: text },
        }),
      ),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: (id: string) =>
      unwrap(api.DELETE("/api/v1/training-items/{item_id}", { params: { path: { item_id: id } } })),
    onSuccess: refresh,
  });
  return { addVersions, upload, caption, remove };
}

export function useStartRun() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (body: RunDraft & { acknowledged_estimate: boolean }) =>
      unwrap(
        api.POST("/api/v1/training-runs", {
          body: { ...DEFAULTS, ...body },
          params: { header: { "Idempotency-Key": `ui-${crypto.randomUUID()}` } },
        }),
      ),
    onSuccess: refresh,
  });
}

/** "2 h 05 min", "12 min", "45 s". */
export function duration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s} s`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min`;
  return `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")} min`;
}
