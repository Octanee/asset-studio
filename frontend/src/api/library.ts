/** Hooks for the project inputs: styles, characters, references and poses (WP-07). */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, api, unwrap, unwrapEmpty, type Schemas } from "./client";

export type Style = Schemas["StyleOut"];
export type StyleAttributes = Schemas["StyleAttributes"];
export type Character = Schemas["CharacterOut"];
export type CharacterAttributes = Schemas["CharacterAttributes"];
export type Reference = Schemas["ReferenceOut"];
export type Pose = Schemas["PoseOut"];
/** A pose as list endpoints type it (keypoints as plain arrays). */
export type PoseRow = Omit<Pose, "keypoints"> & { keypoints: (number[] | null)[] };
export type Job = Schemas["JobDetail"];
export type Point = [number, number, number] | null;

export const REFERENCE_ROLES = [
  "style",
  "character",
  "pose",
  "composition",
  "colour",
  "anatomy",
  "equipment",
  "background",
  "other",
] as const;
export type ReferenceRole = (typeof REFERENCE_ROLES)[number];
export const POSE_VIEWS = ["front", "back", "left", "right", "three_quarter", "other"] as const;
export type PoseView = (typeof POSE_VIEWS)[number];
export const MAX_REFERENCE_BYTES = 30 * 1024 * 1024;

export const libraryKeys = {
  styles: (projectId: string) => ["styles", projectId] as const,
  characters: (projectId: string) => ["characters", projectId] as const,
  references: (projectId: string) => ["references", projectId] as const,
  poses: (projectId: string) => ["poses", projectId] as const,
  job: (jobId: string) => ["jobs", jobId] as const,
};

export const referenceFileUrl = (id: string) => `/api/v1/references/${id}/file`;

export function useStyles(projectId: string | null) {
  return useQuery({
    queryKey: libraryKeys.styles(projectId ?? ""),
    enabled: !!projectId,
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/projects/{project_id}/styles", {
          params: { path: { project_id: projectId ?? "" } },
        }),
      ),
  });
}

export function useCharacters(projectId: string | null) {
  return useQuery({
    queryKey: libraryKeys.characters(projectId ?? ""),
    enabled: !!projectId,
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/projects/{project_id}/characters", {
          params: { path: { project_id: projectId ?? "" } },
        }),
      ),
  });
}

export interface StyleDraft {
  id?: string;
  name: string;
  attributes: StyleAttributes;
}

export function useSaveStyle(projectId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, name, attributes }: StyleDraft) =>
      id
        ? unwrap(
            api.PATCH("/api/v1/styles/{style_id}", {
              params: { path: { style_id: id } },
              body: { name, attributes },
            }),
          )
        : unwrap(
            api.POST("/api/v1/projects/{project_id}/styles", {
              params: { path: { project_id: projectId } },
              body: { name, attributes },
            }),
          ),
    onSuccess: () => void client.invalidateQueries({ queryKey: libraryKeys.styles(projectId) }),
  });
}

export interface CharacterDraft {
  id?: string;
  name: string;
  description: string;
  attributes: CharacterAttributes;
}

export function useSaveCharacter(projectId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: CharacterDraft) =>
      id
        ? unwrap(
            api.PATCH("/api/v1/characters/{character_id}", {
              params: { path: { character_id: id } },
              body,
            }),
          )
        : unwrap(
            api.POST("/api/v1/projects/{project_id}/characters", {
              params: { path: { project_id: projectId } },
              body,
            }),
          ),
    onSuccess: () => void client.invalidateQueries({ queryKey: libraryKeys.characters(projectId) }),
  });
}

export function useArchive(projectId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({ kind, id }: { kind: "style" | "character" | "pose"; id: string }) => {
      if (kind === "style")
        return unwrap(
          api.POST("/api/v1/styles/{style_id}/archive", { params: { path: { style_id: id } } }),
        );
      if (kind === "character")
        return unwrap(
          api.POST("/api/v1/characters/{character_id}/archive", {
            params: { path: { character_id: id } },
          }),
        );
      return unwrap(
        api.POST("/api/v1/poses/{pose_id}/archive", { params: { path: { pose_id: id } } }),
      );
    },
    onSuccess: (_data, { kind }) =>
      void client.invalidateQueries({
        queryKey: (kind === "pose" ? libraryKeys.poses : libraryKeys[`${kind}s`])(projectId),
      }),
  });
}

/** References of a project; with a target, only those linked to that style or character. */
export function useReferences(
  projectId: string | null,
  target?: { type: "style" | "character"; id: string },
) {
  return useQuery({
    queryKey: [...libraryKeys.references(projectId ?? ""), target?.type, target?.id],
    enabled: !!projectId,
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/projects/{project_id}/references", {
          params: {
            path: { project_id: projectId ?? "" },
            query: target ? { target_type: target.type, target_id: target.id } : {},
          },
        }),
      ),
  });
}

export function useUploadReference(projectId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ file, role }: { file: File; role: ReferenceRole }) => {
      if (file.size > MAX_REFERENCE_BYTES) {
        return Promise.reject(
          new ApiError({ status: 413, code: "FILE_TOO_LARGE", detail: "The file is too large." }),
        );
      }
      // The body is the image itself; the server checks the bytes (FR-025).
      return unwrap(
        api.POST("/api/v1/projects/{project_id}/references", {
          params: { path: { project_id: projectId }, query: { role, name: file.name } },
          body: file as unknown as string,
          bodySerializer: (body: unknown) => body as BodyInit,
          headers: { "Content-Type": file.type || "application/octet-stream" },
        }),
      );
    },
    onSettled: () => void client.invalidateQueries({ queryKey: libraryKeys.references(projectId) }),
  });
}

export function useUpdateReference(projectId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, role, archive }: { id: string; role?: ReferenceRole; archive?: boolean }) =>
      archive
        ? unwrap(
            api.POST("/api/v1/references/{reference_id}/archive", {
              params: { path: { reference_id: id } },
            }),
          )
        : unwrap(
            api.PATCH("/api/v1/references/{reference_id}", {
              params: { path: { reference_id: id } },
              body: { role },
            }),
          ),
    onSuccess: () => void client.invalidateQueries({ queryKey: libraryKeys.references(projectId) }),
  });
}

export function useLinkReference(projectId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      referenceId,
      target,
      linked,
    }: {
      referenceId: string;
      target: { type: "style" | "character"; id: string };
      linked: boolean;
    }) => {
      const path = { reference_id: referenceId, target_type: target.type, target_id: target.id };
      return linked
        ? unwrap(
            api.PUT("/api/v1/references/{reference_id}/links/{target_type}/{target_id}", {
              params: { path },
              body: { weight: 1 },
            }),
          )
        : unwrapEmpty(
            api.DELETE("/api/v1/references/{reference_id}/links/{target_type}/{target_id}", {
              params: { path },
            }),
          );
    },
    onSuccess: () => void client.invalidateQueries({ queryKey: libraryKeys.references(projectId) }),
  });
}

export function usePoses(projectId: string | null) {
  return useQuery({
    queryKey: libraryKeys.poses(projectId ?? ""),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/poses", {
          params: { query: projectId ? { project_id: projectId } : {} },
        }),
      ),
  });
}

export interface PoseDraft {
  id?: string;
  name: string;
  view: PoseView;
  aspect: number;
  keypoints: Point[];
  sourceReferenceId?: string | null;
}

export function useSavePose(projectId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, name, view, aspect, keypoints, sourceReferenceId }: PoseDraft) =>
      id
        ? unwrap(
            api.PATCH("/api/v1/poses/{pose_id}", {
              params: { path: { pose_id: id } },
              body: { name, view, aspect, keypoints },
            }),
          )
        : unwrap(
            api.POST("/api/v1/projects/{project_id}/poses", {
              params: { path: { project_id: projectId } },
              body: {
                name,
                view,
                aspect,
                keypoints,
                source_reference_id: sourceReferenceId ?? null,
              },
            }),
          ),
    onSuccess: () => void client.invalidateQueries({ queryKey: libraryKeys.poses(projectId) }),
  });
}

export function useDetectPose() {
  return useMutation({
    mutationFn: ({
      referenceId,
      box,
    }: {
      referenceId: string;
      box?: [number, number, number, number] | null;
    }) =>
      unwrap(
        api.POST("/api/v1/poses:detect", {
          body: { reference_id: referenceId, box: box ?? null },
        }),
      ),
  });
}

/** A job, refreshed while it is queued or running (SSE events also invalidate ["jobs"]). */
export function useJob(jobId: string | null) {
  return useQuery({
    queryKey: libraryKeys.job(jobId ?? ""),
    enabled: !!jobId,
    queryFn: () =>
      unwrap(api.GET("/api/v1/jobs/{job_id}", { params: { path: { job_id: jobId ?? "" } } })),
    refetchInterval: (query) => {
      const state = query.state.data?.state;
      return state === "queued" || state === "running" ? 1000 : false;
    },
  });
}
