import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

export type Schemas = components["schemas"];

/** RFC 9457 problem+json body returned by the API for every error. */
export interface Problem {
  status: number;
  code: string;
  detail: string;
  [extra: string]: unknown;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly problem: Problem;

  constructor(problem: Problem) {
    super(problem.detail);
    this.name = "ApiError";
    this.status = problem.status;
    this.code = problem.code;
    this.problem = problem;
  }
}

/** Same-origin client generated from the OpenAPI document (ADR-003). The session cookie is
 * sent automatically; browsers add Origin, which the API checks on writes (ADR-012). */
export const api = createClient<paths>({
  baseUrl: typeof window === "undefined" ? "" : window.location.origin,
  credentials: "same-origin",
  // Look fetch up per call (tests replace it after this module is loaded).
  fetch: (request) => globalThis.fetch(request),
});

function toProblem(error: unknown, response: Response): Problem {
  if (error && typeof error === "object" && "code" in error && "detail" in error) {
    return { ...(error as Omit<Problem, "status">), status: response.status } as Problem;
  }
  return {
    status: response.status,
    code: response.status === 0 ? "NETWORK" : `HTTP_${response.status}`,
    detail: response.statusText || "The request failed.",
  };
}

/** Returns the data of an openapi-fetch result or throws an ApiError. */
export async function unwrap<T>(
  call: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await call;
  if (!response.ok || data === undefined) throw new ApiError(toProblem(error, response));
  return data;
}
