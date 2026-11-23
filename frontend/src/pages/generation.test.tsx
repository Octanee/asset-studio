/** Generation Studio and Queue (WP-08: FR-030-FR-043, FR-052, RULE-007, RULE-013). */
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";

import { makeQueryClient } from "../api/queries";
import { routes } from "../app/routes";
import { useUi } from "../app/store";
import i18n from "../i18n";
import { batchItems, START, toSpec } from "./GenerationStudio";

type Handler = (request: Request) => unknown;
type Reply = { status?: number; body: unknown };

const checkpoint = {
  id: "sdxl-base-1.0",
  name: "SDXL base 1.0",
  kind: "checkpoint",
  family_id: "sdxl",
  licence: { id: "x", name: "X", commercial_use: "allowed", url: "", notes: "" },
  file_name: "sd_xl_base_1.0.safetensors",
  source_url: null,
  sha256: null,
  bytes: null,
  vram_mb: null,
  origin: "catalogue",
  notes: "",
  status: "installed",
  file_bytes: null,
  verification: "ok",
  verified_at: null,
};
const ready = {
  ready: true,
  problems: [],
  licence_confirmation_required: [],
  workflow: { id: "txt2img+vae", version: 1 },
  models: { checkpoint: "sdxl-base-1.0", vae: "sdxl-vae-fp16-fix" },
  prompts: ["a squat, flat vector"],
  negative: "blurry",
  jobs: 2,
  engine: { available: false, reason: "ENGINE_UNAVAILABLE" },
};
function job(over: Record<string, unknown> = {}) {
  return {
    id: "j1",
    kind: "generate",
    lane: "gpu",
    state: "queued",
    priority: 0,
    params: { plan: { asset_id: "a1", seed: 2004, workflow: { id: "txt2img", version: 1 } } },
    result: {},
    progress: {},
    error: null,
    wait_reason: null,
    attempts: 1,
    max_attempts: 1,
    cancel_requested: false,
    project_id: "p1",
    enqueued_by_actor: "user",
    created_at: "2026-11-23T10:00:00Z",
    started_at: null,
    finished_at: null,
    events: [],
    ...over,
  };
}
const version = {
  id: "v1",
  asset_id: "a1",
  number: 1,
  state: "awaiting_review",
  previous_state: null,
  sha256: "0".repeat(64),
  mime: "image/png",
  bytes: 10,
  width: 1024,
  height: 1024,
  generation_job_id: "j0",
  generation_metadata: { seed: 1998 },
  first_published_at: null,
  deleted_at: null,
  created_at: "2026-11-23T09:00:00Z",
};

function stub(overrides: Record<string, Reply | Handler> = {}) {
  const table: Record<string, Reply | Handler> = {
    "GET /api/v1/session": { body: { actor: "user" } },
    "GET /api/v1/projects": { body: [{ id: "p1", name: "Exerzio", slug: "e", type: "x" }] },
    "GET /api/v1/projects/p1": {
      body: {
        id: "p1",
        name: "Exerzio",
        config: { categories: [{ slug: "exercises", name: "Exercises" }] },
      },
    },
    "GET /api/v1/jobs/summary": { body: { lanes: {}, wait_reasons: {}, workers: [] } },
    "GET /api/v1/jobs": { body: [] },
    "GET /api/v1/models": { body: [checkpoint] },
    "GET /api/v1/projects/p1/styles": { body: [] },
    "GET /api/v1/projects/p1/characters": { body: [] },
    "GET /api/v1/projects/p1/references": { body: [] },
    "GET /api/v1/poses": { body: [] },
    "GET /api/v1/assets": {
      body: [{ id: "a1", name: "Squat", category: "exercises", version_count: 1 }],
    },
    "GET /api/v1/assets/a1/versions": { body: [version] },
    "POST /api/v1/generations:check": { body: ready },
    ...overrides,
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const request = input instanceof Request ? input : new Request(String(input));
      const route = table[`${request.method} ${new URL(request.url).pathname}`];
      if (!route) return new Response("{}", { status: 404 });
      const reply: Reply =
        typeof route === "function" ? { body: await route(request) } : (route as Reply);
      return new Response(JSON.stringify(reply.body), {
        status: reply.status ?? 200,
        headers: { "content-type": "application/json" },
      });
    }),
  );
}

function open(path: string) {
  render(
    <QueryClientProvider client={makeQueryClient()}>
      <RouterProvider router={createMemoryRouter(routes, { initialEntries: [path] })} />
    </QueryClientProvider>,
  );
}

beforeEach(async () => {
  useUi.setState({ theme: "dark", language: "en", projectId: "p1" });
  await i18n.changeLanguage("en");
});
afterEach(() => vi.unstubAllGlobals());

describe("request building", () => {
  it("turns list lines into batch items with an optional extra prompt (FR-034)", () => {
    expect(batchItems("Squat\n\n Plank | elbows under shoulders \n")).toEqual([
      { name: "Squat", prompt: "Squat" },
      { name: "Plank", prompt: "elbows under shoulders" },
    ]);
  });

  it("waits for the checkpoint and the target before asking the API", () => {
    expect(toSpec(START, "p1", "exercises")).toBeNull();
    const d = { ...START, checkpointId: "sdxl-base-1.0" };
    expect(toSpec({ ...d, target: "existing" }, "p1", "exercises")).toBeNull();
    expect(toSpec({ ...d, seed: "42", name: "Squat" }, "p1", "exercises")).toMatchObject({
      asset: { category: "exercises", name: "Squat" },
      seed: 42,
      reference: null,
      batch: [],
    });
    expect(toSpec({ ...d, mode: "batch", items: "" }, "p1", "exercises")).toBeNull();
  });
});

describe("Generation Studio", () => {
  it("asks for a project first", async () => {
    useUi.setState({ projectId: null });
    stub();
    open("/generate");
    expect(await screen.findByText("Choose a project in the top bar first.")).toBeVisible();
  });

  it("shows the checks, queues while the engine is down and follows the job (RULE-013)", async () => {
    const user = userEvent.setup();
    let sent: Record<string, unknown> | null = null;
    let polls = 0;
    stub({
      "POST /api/v1/generations": async (r) => {
        sent = (await r.json()) as Record<string, unknown>;
        return { asset_ids: ["a1"], jobs: [job(), job({ id: "j2" })] };
      },
      "GET /api/v1/jobs/j1": () =>
        ++polls > 1
          ? job({ state: "running", progress: { step: 5, of: 25 } })
          : job({ wait_reason: "ENGINE_UNAVAILABLE" }),
      "GET /api/v1/jobs/j2": () => job({ id: "j2" }),
    });
    open("/generate");
    await user.type(await screen.findByRole("textbox", { name: "Prompt" }), "a squat");
    await user.click(screen.getByRole("button", { name: "2" }));
    const checks = await screen.findByRole("region", { name: "Checks before queueing" });
    expect(await within(checks).findByText("txt2img+vae v1", {}, { timeout: 3000 })).toBeVisible();
    expect(within(checks).getByText("a squat, flat vector")).toBeVisible();
    expect(within(checks).getByText(/jobs wait in the queue/i)).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Queue (2)" }));
    await waitFor(() => expect(sent).not.toBeNull());
    expect(sent).toMatchObject({
      project_id: "p1",
      asset: { category: "exercises" },
      checkpoint_id: "sdxl-base-1.0",
      prompt: "a squat",
      variants: 2,
    });
    const running = await screen.findByRole("region", { name: "Jobs from this screen" });
    expect(
      await within(running).findByText("Waiting: the engine is unavailable", {}, { timeout: 3000 }),
    ).toBeVisible();
    expect(
      await within(running).findByRole("progressbar", { name: "step 5/25" }, { timeout: 4000 }),
    ).toBeVisible();
    expect(within(running).getAllByRole("button", { name: "Cancel" })).toHaveLength(2);
  });

  it("blocks queueing with problems and a pending licence, and says why (RULE-007)", async () => {
    const user = userEvent.setup();
    stub({
      "POST /api/v1/generations:check": {
        body: {
          ...ready,
          ready: false,
          problems: [{ code: "FAMILY_MISMATCH", model_id: "x", detail: "different" }],
          licence_confirmation_required: ["control-lora-openpose-sdxl"],
        },
      },
    });
    open("/generate");
    await user.type(await screen.findByRole("textbox", { name: "Prompt" }), "a squat");
    expect(await screen.findByText(/different families/i, {}, { timeout: 3000 })).toBeVisible();
    expect(screen.getByText(/control-lora-openpose-sdxl needs confirming/i)).toBeVisible();
    expect(screen.getByRole("link", { name: "Open Models" })).toHaveAttribute("href", "/models");
    expect(screen.getByRole("button", { name: "Queue (2)" })).toBeDisabled();
    expect(screen.getByText("Fix the problems in the checks first.")).toBeVisible();
  });

  it("regenerates a version as the next version with a new seed (FR-052)", async () => {
    const user = userEvent.setup();
    let changes: Record<string, unknown> | null = null;
    let versionReads = 0;
    let jobReads = 0;
    stub({
      "POST /api/v1/versions/v1:regenerate": async (r) => {
        changes = (await r.json()) as Record<string, unknown>;
        return { asset_ids: ["a1"], jobs: [job({ id: "j3" })] };
      },
      "GET /api/v1/jobs/j3": () => job({ id: "j3", state: jobReads++ ? "completed" : "running" }),
      "GET /api/v1/assets/a1/versions": () => {
        versionReads += 1;
        return [version];
      },
    });
    open("/generate");
    await user.click(await screen.findByRole("radio", { name: "New version of an asset" }));
    await user.selectOptions(await screen.findByRole("combobox", { name: "Asset" }), "a1");
    expect(await screen.findByText("Creates v2; earlier versions stay as they are.")).toBeVisible();
    const versions = await screen.findByRole("region", { name: "Versions: Squat" });
    expect(await within(versions).findByText("seed 1998")).toBeVisible();
    await user.click(within(versions).getByRole("button", { name: "New version (new seed)" }));
    await waitFor(() => expect(changes).not.toBeNull());
    expect(Object.keys(changes ?? {})).toEqual(["seed"]);
    const running = await screen.findByRole("region", { name: "Jobs from this screen" });
    expect(await within(running).findByText("Running")).toBeVisible();
    // The finished job's version shows up without reloading.
    const before = versionReads;
    expect(await within(running).findByText("Done", {}, { timeout: 4000 })).toBeVisible();
    await waitFor(() => expect(versionReads).toBeGreaterThan(before));
  });

  it("shows why processing failed and retries it (FR-065, T-04R)", async () => {
    const user = userEvent.setup();
    let retried = 0;
    let state = "processing_failed";
    stub({
      "GET /api/v1/assets/a1/versions": () => [
        {
          ...version,
          state,
          processing: {
            steps: [],
            output: null,
            background_removed: false,
            finished_at: null,
            error: {
              code: "PROCESSING_MODEL_MISSING",
              message: "no model",
              step: "remove_background",
            },
          },
        },
      ],
      "POST /api/v1/versions/v1:process": () => {
        retried += 1;
        state = "processing";
        return job({ id: "j4", kind: "remove_background" });
      },
    });
    open("/generate");
    await user.click(await screen.findByRole("radio", { name: "New version of an asset" }));
    await user.selectOptions(await screen.findByRole("combobox", { name: "Asset" }), "a1");
    const versions = await screen.findByRole("region", { name: "Versions: Squat" });
    expect(
      await within(versions).findByText(
        /Processing failed: Background removal needs a segmentation model/,
      ),
    ).toBeVisible();
    await user.click(within(versions).getByRole("button", { name: "Retry processing" }));
    await waitFor(() => expect(retried).toBe(1));
    expect(await within(versions).findByText("Processing", {}, { timeout: 3000 })).toBeVisible();
  });
});

describe("Queue", () => {
  it("lists jobs with progress, errors and filters, and retries failed ones (FR-040, FR-041)", async () => {
    const user = userEvent.setup();
    const retried: string[] = [];
    stub({
      "GET /api/v1/jobs": {
        body: [
          job({ id: "r", state: "running", progress: { step: 14, of: 25 } }),
          job({ id: "f", state: "failed", error: { code: "ENGINE_ERROR", detail: "boom" } }),
          job({ id: "i", state: "interrupted" }),
          job({
            id: "d",
            state: "completed",
            result: { versions: ["v1"] },
            started_at: "2026-11-23T10:00:00Z",
            finished_at: "2026-11-23T10:01:05Z",
          }),
          job({ id: "m", kind: "download", lane: "cpu", params: {}, state: "queued" }),
        ],
      },
      "POST /api/v1/jobs/f/retry": () => {
        retried.push("f");
        return job({ id: "f" });
      },
      "POST /api/v1/jobs/i/retry": () => {
        retried.push("i");
        return job({ id: "i" });
      },
      "GET /api/v1/system/engine": {
        body: {
          available: false,
          reason: "ENGINE_UNAVAILABLE",
          devices: [],
          engine: "comfyui",
          provider: "comfyui",
          features: [],
          version: null,
          agent: {},
        },
      },
    });
    open("/queue");
    const table = await screen.findByRole("table");
    expect(within(table).getByRole("progressbar", { name: "step 14/25" })).toBeVisible();
    expect(within(table).getByText("The engine reported an error.")).toBeVisible();
    expect(within(table).getByText("1 min 5 s")).toBeVisible();
    expect(within(table).getAllByText("Model download").length).toBeGreaterThan(0);
    expect(await within(table).findAllByText("Squat")).toHaveLength(4);
    expect(
      await screen.findByText("GPU jobs are waiting: the engine is unavailable"),
    ).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Failed 1" }));
    expect(within(screen.getByRole("table")).getAllByRole("row")).toHaveLength(2);
    expect(screen.getByRole("button", { name: "Retry" })).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Retry failed (2)" }));
    await waitFor(() => expect(retried.sort()).toEqual(["f", "i"]));
  });
});
