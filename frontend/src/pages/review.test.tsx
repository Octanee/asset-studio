/** Library, asset details, review and compare (WP-10: FR-049-FR-064). */
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";

import { makeQueryClient } from "../api/queries";
import { flatten, metadataDiff, shownVersion } from "../api/review";
import { routes } from "../app/routes";
import { useUi } from "../app/store";
import i18n from "../i18n";

type Handler = (request: Request) => unknown;
type Reply = { status?: number; body: unknown };

function version(over: Record<string, unknown> = {}) {
  return {
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
    generation_metadata: { seed: 1998, steps: 30, prompt: "a squat" },
    first_published_at: null,
    deleted_at: null,
    created_at: "2026-11-23T09:00:00Z",
    processing: { steps: [], output: null, error: null, background_removed: false },
    ...over,
  };
}
const asset = (id: string, name: string, over: Record<string, unknown> = {}) => ({
  id,
  project_id: "p1",
  category: "exercises",
  slug: name.toLowerCase(),
  name,
  tags: [],
  favorite_at: null,
  archived_at: null,
  created_at: "2026-11-23T09:00:00Z",
  version_count: 1,
  collection_ids: [],
  latest_version: version({ id: `v-${id}`, asset_id: id }),
  ...over,
});
const validation = {
  run_id: "r1",
  checked_at: "2026-11-23T09:01:00Z",
  summary: { passed: 1, failed: 1, skipped: 0 },
  results: [
    { rule: "format", status: "passed", details: {} },
    {
      rule: "dimensions",
      status: "failed",
      details: { expected: [768, 768], actual: [1024, 1024] },
    },
  ],
};
const collection = { id: "c1", project_id: "p1", name: "Week 1", created_at: "", asset_count: 0 };

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
    "GET /api/v1/projects/p1/styles": { body: [] },
    "GET /api/v1/projects/p1/characters": { body: [] },
    "GET /api/v1/projects/p1/collections": { body: [collection] },
    "GET /api/v1/assets/tags": { body: [{ tag: "legs", count: 2 }] },
    "GET /api/v1/assets": { body: [asset("a1", "Squat"), asset("a2", "Lunge")] },
    "GET /api/v1/audit": { body: [] },
    ...overrides,
  };
  const calls: { method: string; path: string; search: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const request = input instanceof Request ? input : new Request(String(input));
      const url = new URL(request.url);
      const text = request.method === "GET" ? "" : await request.clone().text();
      calls.push({
        method: request.method,
        path: url.pathname,
        search: url.search,
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

describe("helpers", () => {
  it("shows the published version first, else the newest live one", () => {
    const rows = [
      { id: "3", state: "deleted" },
      { id: "2", state: "awaiting_review" },
      { id: "1", state: "published" },
    ];
    expect(shownVersion(rows)?.id).toBe("1");
    expect(shownVersion(rows.slice(0, 2))?.id).toBe("2");
  });

  it("diffs flattened generation parameters (FR-058)", () => {
    expect(flatten({ size: { width: 1 }, loras: [] })).toEqual({ "size.width": "1", loras: "[]" });
    const diff = metadataDiff({ seed: 1, steps: 30 }, { seed: 2, steps: 30, cfg: 6 });
    expect(diff.filter((d) => !d.same).map((d) => d.key)).toEqual(["cfg", "seed"]);
  });
});

describe("Asset Library", () => {
  it("filters, marks favourites and adds a selection to a collection (FR-050, FR-056, FR-057)", async () => {
    const user = userEvent.setup();
    const calls = stub({
      "PATCH /api/v1/assets/a1": { body: asset("a1", "Squat", { favorite_at: "now" }) },
      "POST /api/v1/collections/c1/assets": { body: { ...collection, asset_count: 2 } },
    });
    open("/library");
    const grid = await screen.findByRole("list", { name: "Assets: 2" });
    expect(within(grid).getByText("Squat")).toBeVisible();

    await user.selectOptions(await screen.findByRole("combobox", { name: "Tag" }), "legs");
    await waitFor(() =>
      expect(calls.some((c) => c.path === "/api/v1/assets" && c.search.includes("tag=legs"))).toBe(
        true,
      ),
    );

    await user.click(screen.getByRole("button", { name: "Favourite: Squat" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ favorite: true }),
    );

    await user.click(screen.getByRole("checkbox", { name: "Select Squat" }));
    await user.click(screen.getByRole("checkbox", { name: "Select Lunge" }));
    const bar = screen.getByRole("region", { name: "Selected assets" });
    expect(within(bar).getByRole("button", { name: "Compare" })).toBeEnabled();
    await user.selectOptions(within(bar).getByRole("combobox", { name: "Collection" }), "c1");
    await user.click(within(bar).getByRole("button", { name: "Add to collection" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path === "/api/v1/collections/c1/assets")?.body).toEqual({
        asset_ids: ["a1", "a2"],
      }),
    );
  });
});

describe("Review", () => {
  const queue = [
    { ...version({ id: "v1" }), asset: asset("a1", "Squat") },
    { ...version({ id: "v2", asset_id: "a2" }), asset: asset("a2", "Lunge") },
  ];
  const reviewRoutes = (over: Record<string, Reply | Handler> = {}) => ({
    "GET /api/v1/versions": { body: queue },
    "GET /api/v1/assets/a1/versions": { body: [version()] },
    "GET /api/v1/assets/a2/versions": { body: [version({ id: "v2", asset_id: "a2" })] },
    "GET /api/v1/versions/v1/validation": { body: validation },
    "GET /api/v1/versions/v2/validation": { body: validation },
    "GET /api/v1/versions/v1/duplicates": { body: [] },
    "GET /api/v1/versions/v2/duplicates": { body: [] },
    "GET /api/v1/versions/v1/comments": {
      body: [
        {
          id: "k1",
          asset_version_id: "v1",
          actor: "mcp",
          body: "Six fingers on the left hand.",
          at: "2026-11-23T09:02:00Z",
        },
      ],
    },
    "GET /api/v1/versions/v2/comments": { body: [] },
    ...over,
  });

  it("shows validation and Claude's comment, approves and moves on (FR-060, FR-061, FR-064)", async () => {
    const user = userEvent.setup();
    const calls = stub(
      reviewRoutes({
        "POST /api/v1/versions/v1/transitions": {
          body: { ...version({ state: "approved" }), history: [] },
        },
      }),
    );
    open("/review");
    expect(await screen.findByText("Waiting for review: 2")).toBeVisible();
    const comment = await screen.findByText("Six fingers on the left hand.");
    expect(within(comment).getByText(/Claude/)).toBeVisible();
    expect(await screen.findByText(/1024×1024 ≠ 768×768/)).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST")?.body).toEqual({
        action: "approve",
        reason: "",
      }),
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Lunge v1" })).toHaveAttribute(
        "aria-current",
        "true",
      ),
    );
  });

  it("comments and rejects with an optional reason", async () => {
    const user = userEvent.setup();
    const calls = stub(
      reviewRoutes({
        "POST /api/v1/versions/v1/transitions": {
          body: { ...version({ state: "rejected" }), history: [] },
        },
        "POST /api/v1/versions/v1/comments": {
          body: { id: "k2", asset_version_id: "v1", actor: "user", body: "ok", at: "" },
        },
      }),
    );
    open("/review");
    await user.type(
      await screen.findByRole("textbox", { name: "Add a comment" }),
      "Knees too far forward",
    );
    await user.click(screen.getByRole("button", { name: "Comment" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path.endsWith("/comments") && c.method === "POST")?.body).toEqual({
        body: "Knees too far forward",
      }),
    );
    await user.click(screen.getByRole("button", { name: "Reject" }));
    await user.type(screen.getByRole("textbox", { name: "Reason (optional)" }), "hands");
    await user.click(screen.getByRole("button", { name: "Reject version" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path.endsWith("/transitions"))?.body).toEqual({
        action: "reject",
        reason: "hands",
      }),
    );
  });

  it("says when nothing waits for review", async () => {
    stub({ "GET /api/v1/versions": { body: [] } });
    open("/review");
    expect(await screen.findByText("Nothing to review")).toBeVisible();
  });
});

describe("Asset details", () => {
  it("needs a reason to withdraw and confirms permanent deletion (FR-054, FR-062)", async () => {
    const user = userEvent.setup();
    const detail = {
      ...asset("a1", "Squat"),
      versions: [
        version({ id: "v2", number: 2, state: "approved" }),
        version({ id: "v1", number: 1, state: "rejected" }),
      ],
    };
    const routesFor = Object.fromEntries(
      ["v1", "v2"].flatMap((id) => [
        [`GET /api/v1/versions/${id}/validation`, { body: validation }],
        [`GET /api/v1/versions/${id}/duplicates`, { body: [] }],
        [`GET /api/v1/versions/${id}/comments`, { body: [] }],
      ]),
    ) as Record<string, Reply>;
    const calls = stub({
      ...routesFor,
      "GET /api/v1/assets/a1": { body: detail },
      "DELETE /api/v1/versions/v1": { body: { ...version({ state: "deleted" }), history: [] } },
    });
    open("/library/a1");
    expect(await screen.findByRole("heading", { name: /Version 2/ })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Withdraw approval" }));
    const submit = screen.getAllByRole("button", { name: "Withdraw approval" }).at(-1);
    expect(submit).toBeDisabled();
    await user.type(screen.getByRole("textbox", { name: /required/ }), "wrong knee angle");
    expect(submit).toBeEnabled();

    await user.click(screen.getByRole("button", { name: /^v1/ }));
    await user.click(await screen.findByRole("button", { name: "Delete permanently" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/cannot be recovered/)).toBeVisible();
    await user.click(within(dialog).getByRole("button", { name: "Delete permanently" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "DELETE")?.search).toBe("?confirm=v1"),
    );
  });
});

describe("Compare", () => {
  it("shows two versions and only the changed parameters (FR-058)", async () => {
    const user = userEvent.setup();
    stub({
      "GET /api/v1/versions/v1": { body: { ...version(), history: [] } },
      "GET /api/v1/versions/v2": {
        body: {
          ...version({
            id: "v2",
            number: 2,
            generation_metadata: { seed: 7, steps: 30, prompt: "a squat" },
          }),
          history: [],
        },
      },
      "GET /api/v1/assets/a1": { body: { ...asset("a1", "Squat"), versions: [] } },
    });
    open("/review/compare?a=v1&b=v2");
    const table = await screen.findByRole("table");
    expect(within(table).getAllByRole("row")).toHaveLength(2); // the header and the seed
    expect(within(table).getByText("seed")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Swipe" }));
    expect(screen.getByRole("slider", { name: "Divider position" })).toBeVisible();
  });
});
