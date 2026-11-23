/** Hooks for the model registry (WP-12: FR-080-FR-084, RULE-007, RULE-008). */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap, type Schemas } from "./client";

export type ModelRow = Schemas["ModelOut"];
export type JobRow = Schemas["JobOut"];
export const MODEL_KINDS = [
  "checkpoint",
  "lora",
  "controlnet",
  "ip_adapter",
  "clip_vision",
  "vae",
  "pose",
  "segmentation",
] as const;
export type ModelKind = (typeof MODEL_KINDS)[number];

export const modelKeys = {
  all: ["models"] as const,
  list: (projectId: string | null) => ["models", projectId ?? ""] as const,
  // Under "jobs" so live job events refresh it.
  activeJobs: ["jobs", "model-work"] as const,
};

export function useModels(projectId: string | null) {
  return useQuery({
    queryKey: modelKeys.list(projectId),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/models", {
          params: { query: projectId ? { project_id: projectId } : {} },
        }),
      ),
  });
}

/** Running and queued downloads and checks, by model id. */
export function useModelJobs() {
  return useQuery({
    queryKey: modelKeys.activeJobs,
    queryFn: async () => {
      const rows = await Promise.all(
        (["download", "verify_model"] as const).map((kind) =>
          unwrap(api.GET("/api/v1/jobs", { params: { query: { kind, limit: 50 } } })),
        ),
      );
      const active: Record<string, JobRow> = {};
      for (const job of rows.flat()) {
        const id = String((job.params as { model_id?: string }).model_id ?? "");
        if ((job.state === "queued" || job.state === "running") && id && !active[id]) {
          active[id] = job;
        }
      }
      return active;
    },
    refetchInterval: (query) => (Object.keys(query.state.data ?? {}).length ? 2000 : 15_000),
  });
}

function useRefresh() {
  const client = useQueryClient();
  return () => {
    void client.invalidateQueries({ queryKey: modelKeys.all });
    void client.invalidateQueries({ queryKey: modelKeys.activeJobs });
  };
}

export function useRescan() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/models:rescan")),
    onSuccess: refresh,
  });
}

export function useDownload() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (model: ModelRow) =>
      unwrap(
        api.POST("/api/v1/models/{model_id}:download", {
          params: { path: { model_id: model.id } },
          // The confirmation repeats exactly what the user saw (RULE-008).
          body: {
            file_name: model.file_name,
            source_url: model.source_url ?? "",
            bytes: model.bytes ?? 0,
          },
        }),
      ),
    onSettled: refresh,
  });
}

export function useVerify() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (modelId: string) =>
      unwrap(
        api.POST("/api/v1/models/{model_id}:verify", { params: { path: { model_id: modelId } } }),
      ),
    onSettled: refresh,
  });
}

export function useCancelJob() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (jobId: string) =>
      unwrap(api.POST("/api/v1/jobs/{job_id}/cancel", { params: { path: { job_id: jobId } } })),
    onSettled: refresh,
  });
}

export function useSetFamily() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: ({ modelId, familyId }: { modelId: string; familyId: string | null }) =>
      unwrap(
        api.PATCH("/api/v1/models/{model_id}", {
          params: { path: { model_id: modelId } },
          body: { family_id: familyId },
        }),
      ),
    onSuccess: refresh,
  });
}

export function useAcknowledgeLicence(projectId: string) {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: ({ modelId, note }: { modelId: string; note: string }) =>
      unwrap(
        api.POST("/api/v1/projects/{project_id}/licence-acknowledgements", {
          params: { path: { project_id: projectId } },
          body: { model_id: modelId, note },
        }),
      ),
    onSuccess: refresh,
  });
}

export function formatSize(bytes: number | null | undefined): string {
  if (!bytes) return "—";
  const gb = bytes / 1024 ** 3;
  return gb >= 1 ? `${gb.toFixed(2)} GB` : `${Math.ceil(bytes / 1024 ** 2)} MB`;
}
