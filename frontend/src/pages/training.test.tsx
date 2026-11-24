/** LoRA training screen (WP-13: FR-070-FR-075, RULE-016, RULE-017). */
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";

import { makeQueryClient } from "../api/queries";
import { duration } from "../api/training";
import { routes } from "../app/routes";
import { useUi } from "../app/store";
import i18n from "../i18n";

type Handler = (request: Request) => unknown;
type Reply = { status?: number; body: unknown };

const dataset = {
  id: "d1",
  project_id: "p1",
  name: "Exerzio woman",
  trigger_word: "exz_woman",
  archived_at: null,
  created_at: "2026-11-24T08:00:00Z",
  images: 5,
};
const item = (n: number) => ({
  id: `i${n}`,
  dataset_id: "d1",
  source: "asset_version",
  asset_version_id: `v${n}`,
  width: 512,
  height: 512,
  caption: `Plank ${n}`,
  created_at: "2026-11-24T08:00:00Z",
});
const model = (id: string, family: string) => ({
  id,
  name: id,
  kind: "checkpoint",
  family_id: family,
  status: "installed",
  licence_id: "mit",
});
function estimate(body: { family: string; steps?: number | null }) {
  const xl = body.family === "sdxl";
  const steps = body.steps ?? (xl ? 300 : 500);
  return {
    family: body.family,
    steps,
    resolution: xl ? 768 : 512,
    seconds: xl ? 180 + steps * 30 : 60 + steps * 0.6,
    seconds_per_step: xl ? 30 : 0.6,
    vram_mb: 6144,
    recommended_vram_mb: xl ? 12000 : 6000,
    warning: xl,
    images: 5,
    default_steps: xl ? 300 : 500,
    min_steps: 300,
    max_steps: 3000,
  };
}
const runningJob = {
  id: "j1",
  kind: "train",
  lane: "gpu",
  state: "running",
  params: {},
  result: {},
  progress: { state: "training", step: 120, of: 500 },
  error: null,
  wait_reason: null,
};
const run = {
  id: "r1",
  project_id: "p1",
  dataset_id: "d1",
  family_id: "sd15",
  base_model_id: "v15",
  params: { steps: 500 },
  images: 5,
  estimate: { seconds: 360 },
  acknowledged_estimate: false,
  output_name: "exz-woman-sd15-1",
  job_id: "j1",
  output_model_id: null,
  created_by_actor: "user",
  created_at: "2026-11-24T08:00:00Z",
  job: runningJob,
};

function stub(overrides: Record<string, Reply | Handler> = {}) {
  const table: Record<string, Reply | Handler> = {
    "GET /api/v1/session": { body: { actor: "user" } },
    "GET /api/v1/projects": { body: [{ id: "p1", name: "Exerzio", slug: "e", type: "x" }] },
    "GET /api/v1/jobs/summary": { body: { lanes: {}, wait_reasons: {}, workers: [] } },
    "GET /api/v1/projects/p1/datasets": { body: [dataset] },
    "GET /api/v1/datasets/d1/items": { body: [1, 2, 3, 4, 5].map(item) },
    "GET /api/v1/models": { body: [model("v15", "sd15"), model("xl", "sdxl")] },
    "GET /api/v1/versions": { body: [] },
    "GET /api/v1/training-runs": { body: [] },
    "POST /api/v1/training-runs:estimate": async (r) =>
      estimate((await r.clone().json()) as { family: string; steps?: number | null }),
    "POST /api/v1/training-runs": { status: 202, body: run },
    "PATCH /api/v1/training-items/i1": async (r) => ({
      ...item(1),
      ...((await r.clone().json()) as object),
    }),
    ...overrides,
  };
  const calls: { method: string; path: string; body: unknown; type: string | null }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const request = input instanceof Request ? input : new Request(String(input));
      const url = new URL(request.url);
      const type = request.headers.get("Content-Type");
      const json = request.method !== "GET" && !!type?.includes("json");
      const text = json ? await request.clone().text() : "";
      calls.push({
        method: request.method,
        path: url.pathname,
        body: text ? (JSON.parse(text) as unknown) : null,
        type,
      });
      const route = table[`${request.method} ${url.pathname}`];
      if (!route) return new Response("{}", { status: 404 });
      const reply: Reply =
        typeof route === "function" ? { body: await route(request) } : (route as Reply);
      return new Response(JSON.stringify(reply.body), {
        status: reply.status ?? 200,
        headers: { "content-type": "application/json" },
      });
    }),
  );
  return calls;
}

function open() {
  render(
    <QueryClientProvider client={makeQueryClient()}>
      <RouterProvider router={createMemoryRouter(routes, { initialEntries: ["/training"] })} />
    </QueryClientProvider>,
  );
}

function posted(calls: ReturnType<typeof stub>) {
  return calls.find((c) => c.method === "POST" && c.path === "/api/v1/training-runs")?.body;
}

beforeEach(async () => {
  useUi.setState({ theme: "dark", language: "en", projectId: "p1" });
  await i18n.changeLanguage("en");
});
afterEach(() => vi.unstubAllGlobals());

describe("Training (FR-070-FR-075)", () => {
  it("shows the dataset with editable captions and the SD 1.5 estimate", async () => {
    const user = userEvent.setup();
    const calls = stub();
    open();
    const caption = await screen.findByRole("textbox", { name: "Caption of image 1" });
    await user.clear(caption);
    await user.type(caption, "woman, side view");
    await user.tab();
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({
        caption: "woman, side view",
      }),
    );
    expect(await screen.findByText("6 min")).toBeVisible();
    expect(screen.getByText(/500 · 512 px · images: 5/)).toBeVisible();
    const start = screen.getByRole("button", { name: "Start training" });
    await waitFor(() => expect(start).toBeEnabled());
    await user.click(start);
    await waitFor(() =>
      expect(posted(calls)).toMatchObject({
        dataset_id: "d1",
        family: "sd15",
        base_model_id: "v15",
      }),
    );
  });

  it("asks to acknowledge the SDXL estimate before starting (RULE-016)", async () => {
    const user = userEvent.setup();
    const calls = stub();
    open();
    await user.click(await screen.findByRole("radio", { name: "SDXL" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("about 2 h 33 min");
    const start = screen.getByRole("button", { name: "Start training" });
    expect(start).toBeDisabled();
    expect(screen.getByText("Confirm the time estimate first (RULE-016).")).toBeVisible();
    await user.click(within(alert).getByRole("checkbox"));
    await waitFor(() => expect(start).toBeEnabled());
    await user.click(start);
    await waitFor(() =>
      expect(posted(calls)).toMatchObject({
        family: "sdxl",
        base_model_id: "xl",
        acknowledged_estimate: true,
      }),
    );
  });

  it("shows a run's progress and cancels it (FR-074)", async () => {
    const user = userEvent.setup();
    const calls = stub({
      "GET /api/v1/training-runs": { body: [run] },
      "POST /api/v1/jobs/j1/cancel": { body: { ...runningJob, state: "cancelled" } },
    });
    open();
    expect(await screen.findByRole("progressbar")).toHaveAttribute("aria-valuenow", "120");
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/api/v1/jobs/j1/cancel")).toBe(true));
  });

  it("uploads images as raw bodies", async () => {
    const user = userEvent.setup();
    const calls = stub({ "POST /api/v1/datasets/d1/items": { status: 201, body: item(6) } });
    open();
    const upload = await screen.findByLabelText("Upload images");
    const file = new File([new Uint8Array([137, 80, 78, 71])], "pose.png", { type: "image/png" });
    await user.upload(upload, file);
    await waitFor(() =>
      expect(
        calls.find((c) => c.method === "POST" && c.path === "/api/v1/datasets/d1/items")?.type,
      ).toBe("image/png"),
    );
  });
});

describe("duration", () => {
  it("reads like a person would say it", () => {
    expect([duration(45), duration(360), duration(9180)]).toEqual(["45 s", "6 min", "2 h 33 min"]);
  });
});
