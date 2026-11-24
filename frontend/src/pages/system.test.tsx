/** Dashboard, settings, backups, audit log and queue pause (WP-16: FR-100, FR-110-FR-112,
 * FR-115). */
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";

import { makeQueryClient } from "../api/queries";
import { routes } from "../app/routes";
import { useUi } from "../app/store";
import i18n from "../i18n";

type Handler = (request: Request) => unknown;
type Reply = { status?: number; body: unknown };

const backup = {
  name: "asset-studio-backup-20261124-080000.zip",
  bytes: 5 * 1024 * 1024,
  readable: true,
  created_at: "2026-11-24T08:00:00+00:00",
  app_version: "0.1.0",
  schema_revision: "0010",
  totals: { tables: 30, rows: 120, files: 12, file_bytes: 4000000 },
  models: 2,
};

function status(empty: boolean) {
  return {
    api: { status: "ok", version: "0.1.0" },
    engine: {
      provider: "fake",
      engine: "fake",
      available: true,
      version: "1",
      reason: null,
      detail: null,
      devices: [],
      features: [],
      agent: {},
    },
    database: { ok: true, schema_revision: "0010", head_revision: "0010" },
    queue: { lanes: {}, wait_reasons: {}, workers: [{ worker_id: "w" }], paused: false },
    storage: {
      volume: "asset-data",
      files: 12,
      bytes: 4000000,
      free_bytes: 1e10,
      total_bytes: 2e10,
      empty,
    },
    consistency: { missing: 0, orphans: 1, missing_versions: [] },
    backups: { configured: true, last: backup, due: false },
    locations: {
      export_roots: 1,
      models_folder: true,
      engine_url: "http://host.docker.internal:8188",
    },
    mcp: { configured: true, port: 8411 },
  };
}

const job = (kind: string, state = "queued") => ({
  id: `job-${kind}`,
  kind,
  lane: "cpu",
  state,
  params: {},
  result: {},
  progress: {},
  error: null,
  wait_reason: null,
  events: [],
});

function stub(overrides: Record<string, Reply | Handler> = {}) {
  const table: Record<string, Reply | Handler> = {
    "GET /api/v1/session": { body: { actor: "user" } },
    "GET /api/v1/projects": { body: [{ id: "p1", name: "Exerzio", slug: "e", type: "x" }] },
    "GET /api/v1/jobs/summary": {
      body: { lanes: { gpu: { running: 1, queued: 3 } }, wait_reasons: {}, workers: [] },
    },
    "GET /api/v1/jobs": { body: [] },
    "GET /api/v1/assets": { body: [] },
    "GET /api/v1/settings": { body: { queue_paused: false } },
    "PATCH /api/v1/settings": async (r) => (await r.clone().json()) as unknown,
    "GET /api/v1/system/status": { body: status(false) },
    "GET /api/v1/backups": { body: { configured: true, items: [backup] } },
    "POST /api/v1/backups": { status: 202, body: job("backup") },
    "POST /api/v1/backups:restore": { status: 202, body: job("restore") },
    "GET /api/v1/jobs/job-backup": { body: job("backup", "completed") },
    "GET /api/v1/jobs/job-restore": { body: job("restore", "completed") },
    "GET /api/v1/audit/actions": { body: ["job.enqueued", "setting.changed"] },
    "GET /api/v1/audit": {
      body: [
        {
          id: "e1",
          at: "2026-11-24T08:00:00Z",
          actor: "mcp",
          project_id: "p1",
          action: "review_comment.created",
          subject_type: "asset_version",
          subject_id: "v1",
          data: { body: "ok" },
        },
      ],
    },
    "GET /api/v1/dashboard": {
      body: {
        versions_by_state: { awaiting_review: 4, approved: 2 },
        attention: {
          awaiting_review: 4,
          processing_failed: 1,
          failed_jobs: 2,
          licence_warnings: 0,
          backup_due: true,
        },
        latest_versions: [
          {
            id: "v1",
            asset_id: "a1",
            asset_name: "Plank",
            category: "core",
            number: 3,
            state: "awaiting_review",
            created_at: "2026-11-24T08:00:00Z",
          },
        ],
        failed_jobs: [
          {
            id: "j9",
            kind: "generate",
            finished_at: "2026-11-24T07:00:00Z",
            code: "X",
            message: "out of memory",
          },
        ],
        last_backup: null,
      },
    },
    ...overrides,
  };
  const calls: {
    method: string;
    path: string;
    query: string;
    key: string | null;
    body: unknown;
  }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const request = input instanceof Request ? input : new Request(String(input));
      const url = new URL(request.url);
      const text = request.method === "GET" ? "" : await request.clone().text();
      calls.push({
        method: request.method,
        path: url.pathname,
        query: url.search,
        key: request.headers.get("Idempotency-Key"),
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

describe("Dashboard (FR-100)", () => {
  it("shows what needs attention, the latest versions, failures and activity", async () => {
    stub();
    open("/");
    const review = await screen.findByRole("link", { name: /Awaiting review\s*4/ });
    expect(review).toHaveAttribute("href", "/review");
    expect(review).toHaveAttribute("data-attention", "true");
    expect(screen.getByRole("link", { name: /Last backup.*No backup yet/ })).toHaveAttribute(
      "data-attention",
      "true",
    );
    expect(screen.getByRole("link", { name: /Queue\s*1 \/ 3/ })).toBeVisible();
    expect(screen.getByRole("link", { name: /Plank v3/ })).toHaveAttribute("href", "/library/a1");
    expect(screen.getByText(/out of memory/)).toBeVisible();
    expect(await screen.findByText(/Claude/)).toBeVisible();
    expect(screen.getByRole("link", { name: "Batch" })).toHaveAttribute(
      "href",
      "/generate?mode=batch",
    );
  });
});

describe("Remembered project", () => {
  it("is forgotten when it no longer exists, so the dashboard asks for a project", async () => {
    stub();
    useUi.setState({ projectId: "gone" });
    open("/");
    expect(await screen.findByText(/Choose a project/i)).toBeVisible();
    expect(useUi.getState().projectId).toBeNull();
  });
});

describe("Backups (FR-111, FR-112)", () => {
  it("creates a backup with an idempotency key and follows its job", async () => {
    const user = userEvent.setup();
    const calls = stub();
    open("/settings/data");
    expect(await screen.findByText(backup.name)).toBeVisible();
    expect(screen.getByText("files: 12, rows: 120, models: 2")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Create backup" }));
    await waitFor(() =>
      expect(calls.find((x) => x.method === "POST" && x.path === "/api/v1/backups")?.key).toMatch(
        /^ui-/,
      ),
    );
    expect(await screen.findByText("Done")).toBeVisible();
  });

  it("does not offer a restore while the data location has projects", async () => {
    stub();
    open("/settings/data");
    const restore = await screen.findByRole("button", { name: "Restore" });
    await waitFor(() => expect(restore).toBeDisabled());
    expect(screen.getAllByText(/only into an empty data location/)[0]).toBeVisible();
  });

  it("asks before restoring a backup into a fresh install", async () => {
    const user = userEvent.setup();
    const calls = stub({ "GET /api/v1/system/status": { body: status(true) } });
    open("/settings/data");
    const restore = await screen.findByRole("button", { name: "Restore" });
    await waitFor(() => expect(restore).toBeEnabled());
    await user.click(restore);
    expect(calls.some((c) => c.path === "/api/v1/backups:restore")).toBe(false);
    await user.click(screen.getByRole("button", { name: "Restore now" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path === "/api/v1/backups:restore")?.body).toEqual({
        name: backup.name,
      }),
    );
  });
});

describe("Settings", () => {
  it("shows the MCP connection command without the token", async () => {
    stub();
    open("/settings/mcp");
    expect(
      await screen.findByText(/claude mcp add --transport http asset-studio/),
    ).toHaveTextContent("http://127.0.0.1:8411/mcp");
    expect(await screen.findByText(/Claude can connect/)).toBeVisible();
  });

  it("filters the audit log by project, actor and action (FR-115)", async () => {
    const user = userEvent.setup();
    const calls = stub();
    open("/settings/audit");
    const table = await screen.findByRole("table");
    expect(within(table).getByText("Claude")).toBeVisible();
    await user.selectOptions(screen.getByRole("combobox", { name: "Actor" }), "mcp");
    await user.selectOptions(screen.getByRole("combobox", { name: "Project" }), "p1");
    await waitFor(() => {
      const last = calls.filter((c) => c.path === "/api/v1/audit").at(-1)?.query ?? "";
      expect(last).toContain("actor=mcp");
      expect(last).toContain("project_id=p1");
    });
    expect(await screen.findByRole("option", { name: "setting.changed" })).toBeInTheDocument();
  });

  it("pauses the queue from the Queue screen", async () => {
    const user = userEvent.setup();
    const calls = stub();
    open("/queue");
    await user.click(await screen.findByRole("button", { name: "Pause queue" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ queue_paused: true }),
    );
    expect(await screen.findByRole("button", { name: "Resume queue" })).toBeVisible();
  });
});
