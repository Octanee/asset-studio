/** Export and publish (WP-11: FR-090-FR-094, RULE-004, DD-006). */
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";

import { makeQueryClient } from "../api/queries";
import { routes } from "../app/routes";
import { useUi } from "../app/store";
import i18n from "../i18n";

type Handler = (request: Request) => unknown;
type Reply = { status?: number; body: unknown };

const asset = { id: "a1", project_id: "p1", category: "legs", slug: "squat", name: "Squat" };
const approved = {
  id: "v1",
  asset_id: "a1",
  number: 1,
  state: "approved",
  previous_state: null,
  sha256: "0".repeat(64),
  mime: "image/png",
  bytes: 1,
  width: 64,
  height: 64,
  generation_job_id: null,
  generation_metadata: {},
  first_published_at: null,
  deleted_at: null,
  created_at: "2026-11-23T09:00:00Z",
  asset,
};
const preset = {
  id: "pr1",
  project_id: "p1",
  name: "Web",
  archived_at: null,
  created_at: "",
  updated_at: "",
  definition: {
    format: "webp",
    sizes: [{ suffix: "", width: 512, height: 512 }],
    naming: "{asset}-{view}{suffix}",
    folders: "",
    background: "keep",
    resize: "contain",
    optimize: true,
    quality: 90,
    metadata: "none",
  },
};
const target = {
  id: "t1",
  project_id: "p1",
  name: "App",
  root_name: "exports",
  subdir: "app",
  available: true,
  archived_at: null,
  created_at: "",
};
const plan = {
  id: "pl1",
  project_id: "p1",
  preset_id: "pr1",
  target_id: "t1",
  items: [
    {
      version_id: "v1",
      asset_id: "a1",
      asset: "Squat",
      number: 1,
      state: "approved",
      files: [{ path: "squat-main.webp", exists: true, existing_sha256: "f".repeat(64) }],
    },
  ],
  skipped: [],
  files: 1,
  overwrites: ["squat-main.webp"],
  created_at: "",
  used_at: null,
  job_id: null,
};
const doneJob = {
  id: "j1",
  kind: "export",
  lane: "cpu",
  state: "completed",
  params: {},
  result: { published: [{ version_id: "v1" }], failed: [] },
  progress: {},
  error: null,
  events: [],
};

function stub(overrides: Record<string, Reply | Handler> = {}) {
  const table: Record<string, Reply | Handler> = {
    "GET /api/v1/session": { body: { actor: "user" } },
    "GET /api/v1/projects": { body: [{ id: "p1", name: "Exerzio", slug: "e", type: "x" }] },
    "GET /api/v1/jobs/summary": { body: { lanes: {}, wait_reasons: {}, workers: [] } },
    "GET /api/v1/versions": (r) =>
      new URL(r.url).searchParams.get("state") === "approved" ? [approved] : [],
    "GET /api/v1/projects/p1/collections": { body: [] },
    "GET /api/v1/projects/p1/presets": { body: [preset] },
    "GET /api/v1/projects/p1/targets": { body: [target] },
    "GET /api/v1/export-roots": { body: [{ id: "0", name: "exports" }] },
    "GET /api/v1/publications": { body: [] },
    "POST /api/v1/publications:plan": { status: 201, body: plan },
    "POST /api/v1/publications": { status: 202, body: { ...doneJob, state: "queued" } },
    "GET /api/v1/jobs/j1": { body: doneJob },
    ...overrides,
  };
  const calls: { method: string; path: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const request = input instanceof Request ? input : new Request(String(input));
      const url = new URL(request.url);
      const text = request.method === "GET" ? "" : await request.clone().text();
      calls.push({
        method: request.method,
        path: url.pathname,
        body: text ? (JSON.parse(text) as unknown) : null,
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

describe("Export and publish", () => {
  it("plans files and publishes only after each overwrite is confirmed (RULE-004)", async () => {
    const user = userEvent.setup();
    const calls = stub();
    open("/publish?versions=v1");
    expect(await screen.findByRole("checkbox", { name: /Squat v1/ })).toBeChecked();
    expect(screen.getByRole("button", { name: "Publish" })).toBeDisabled();

    await user.click(await screen.findByRole("button", { name: "Plan files" }));
    expect(await screen.findByText("squat-main.webp")).toBeVisible();
    expect(screen.getByRole("alert")).toHaveTextContent("will be replaced: 1");
    const button = screen.getByRole("button", { name: "Publish versions: 1" });
    expect(button).toBeDisabled();
    expect(calls.find((c) => c.path === "/api/v1/publications:plan")?.body).toMatchObject({
      version_ids: ["v1"],
      preset_id: "pr1",
      target_id: "t1",
      whole_project: false,
    });

    await user.click(screen.getByRole("checkbox", { name: "Confirm overwriting squat-main.webp" }));
    expect(button).toBeEnabled();
    await user.click(button);
    await waitFor(() =>
      expect(
        calls.find((c) => c.method === "POST" && c.path === "/api/v1/publications")?.body,
      ).toEqual({ plan_id: "pl1", confirm_overwrites: ["squat-main.webp"] }),
    );
    expect(await screen.findByText(/Published versions: 1/)).toBeVisible();
  });

  it("creates a preset with several sizes (FR-090)", async () => {
    const user = userEvent.setup();
    const calls = stub({
      "GET /api/v1/projects/p1/presets": { body: [] },
      "POST /api/v1/projects/p1/presets": { status: 201, body: preset },
    });
    open("/publish");
    expect(await screen.findByText("No presets yet.")).toBeVisible();
    await user.click(screen.getAllByRole("button", { name: "New" })[0] as HTMLElement);
    await user.type(screen.getByRole("textbox", { name: "Preset name" }), "App");
    await user.click(screen.getByRole("button", { name: "Add size" }));
    await user.click(screen.getByRole("button", { name: "Save preset" }));
    await waitFor(() => {
      const body = calls.find(
        (c) => c.method === "POST" && c.path === "/api/v1/projects/p1/presets",
      )?.body as { name: string; definition: { sizes: unknown[] } } | undefined;
      expect(body?.name).toBe("App");
      expect(body?.definition.sizes).toHaveLength(2);
    });
  });

  it("explains when no export folder is configured (ADR-013)", async () => {
    stub({
      "GET /api/v1/export-roots": { body: [] },
      "GET /api/v1/projects/p1/targets": { body: [] },
    });
    open("/publish");
    expect(await screen.findByText(/No export folder is configured/)).toBeVisible();
    expect(screen.getByRole("button", { name: "Plan files" })).toBeDisabled();
  });
});
