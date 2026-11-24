/** Hooks for the SVG Studio (WP-14: FR-045-FR-047, UC-014). */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap, type Schemas } from "./client";

export type SvgTemplate = Schemas["TemplateOut"];
export type SvgParam = Schemas["ParamOut"];
export type SvgSpec = Schemas["SvgSpec"];
export type SvgPreview = Schemas["SvgPreviewOut"];
export type SvgParams = Record<string, string | number>;

export const SVG_MIME = "image/svg+xml";

/** The cleaned SVG as an image source: an <img> never runs anything inside an SVG. */
export const svgDataUrl = (svg: string) =>
  `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;

export function useSvgTemplates() {
  return useQuery({
    queryKey: ["svg", "templates"],
    queryFn: () => unwrap(api.GET("/api/v1/svg/templates")),
    staleTime: Infinity, // versioned code: it only changes with the app
  });
}

/** The real output for these parameters, rendered by the server (deterministic). */
export function useSvgPreview(spec: SvgSpec | null) {
  return useQuery({
    queryKey: ["svg", "preview", JSON.stringify(spec)],
    enabled: !!spec,
    queryFn: () => unwrap(api.POST("/api/v1/svg:preview", { body: spec as SvgSpec })),
    // Keep the last picture while the next one renders, so the preview does not flicker.
    placeholderData: keepPreviousData,
  });
}

export function useCreateSvg() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (spec: SvgSpec) => unwrap(api.POST("/api/v1/svg", { body: spec })),
    onSettled: () => {
      void client.invalidateQueries({ queryKey: ["jobs"] });
      void client.invalidateQueries({ queryKey: ["assets"] });
    },
  });
}
