/** Projects, new project, Claude's drafts and project settings (WP-16 part 2: FR-001-FR-008,
 * RULE-005, RULE-010). */
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";

import { makeQueryClient } from "../api/queries";
import { routes } from "../app/routes";
import { useUi } from "../app/store";
import i18n from "../i18n";
import { slugify } from "./ProjectEditor";

/** A handler returns the body; a ``__status`` field sets the response status. */
type Handler = (request: Request) => unknown;
type Reply = { status?: number; body: unknown };

const config = {
  schema_version: 1,
  name: "Exerzio",
  description: "",
  type: "illustration",
  languages: ["pl"],
  intended_use: "commercial",
  categories: [{ slug: "core", name: "Brzuch" }],
  naming: "{asset}-{view}",
};
const project = {
  id: "p1",
  slug: "exerzio",
  name: "Exerzio",
  type: "illustration",
  intended_use: "commercial",
  mcp_can_decide: false,
  current_config_version: 2,
  archived_at: null,
  created_at: "2026-11-24T08:00:00Z",
};
const draft = {
  id: "d1",
  status: "pending",
  description: "Stretching illustrations",
  config: { ...config, name: "Stretch" },
  assumptions: ["flat vector"],
  missing: ["brand colours"],
  created_by_actor: "mcp",
  project_id: null,
  created_at: "2026-11-24T08:00:00Z",
  problems: [],
};
const version = (n: number, cfg: object) => ({
  version: n,
  schema_version: 1,
  created_by_actor: "user",
  note: "",
  created_at: "2026-11-24T08:00:00Z",
  config: cfg,
});

/** The schema check: a name and valid category slugs. */
async function check(r: Request) {
  const { config: c } = (await r.clone().json()) as {
    config: { name?: string; categories?: { slug: string }[] };
  };
  const problems: { loc: (string | number)[]; msg: string }[] = [];
  if (!c.name) problems.push({ loc: ["name"], msg: "String should have at least 1 character" });
  (c.categories ?? []).forEach((cat, i) => {
    if (!/^[a-z0-9][a-z0-9-]*$/.test(cat.slug))
      problems.push({ loc: ["categories", i, "slug"], msg: "bad slug" });
  });
  return { valid: problems.length === 0, problems };
}

function stub(overrides: Record<string, Reply | Handler> = {}) {
  const table: Record<string, Reply | Handler> = {
    "GET /api/v1/session": { body: { actor: "user" } },
    "GET /api/v1/projects": {
      body: [project, { ...project, id: "p2", slug: "lydki", name: "Łydki" }],
    },
    "GET /api/v1/jobs/summary": { body: { lanes: {}, wait_reasons: {}, workers: [] } },
    "GET /api/v1/dashboard/projects": {
      body: [
        { project_id: "p1", assets: 3, versions: 7, awaiting_review: 2, approved: 4, published: 1 },
      ],
    },
    "GET /api/v1/projects/drafts": { body: [draft] },
    "GET /api/v1/projects/drafts/d1": { body: draft },
    "POST /api/v1/projects:validate": check,
    "POST /api/v1/projects": { status: 201, body: { ...project, id: "p2", config } },
    "POST /api/v1/projects/drafts/d1/confirm": {
      status: 201,
      body: { ...project, id: "p3", config },
    },
    "GET /api/v1/projects/p1": { body: { ...project, config } },
    "GET /api/v1/projects/p2": { body: { ...project, id: "p2", config } },
    "GET /api/v1/projects/p3": { body: { ...project, id: "p3", config } },
    "GET /api/v1/projects/p1/config/versions": {
      body: [version(2, config), version(1, { ...config, naming: "{asset}" })],
    },
    "PATCH /api/v1/projects/p1/settings": { body: { ...project, mcp_can_decide: true } },
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
      let status = 200;
      let body: unknown;
      if (typeof route === "function") {
        body = await route(request);
        const asked = (body as { __status?: number } | null)?.__status;
        if (asked) status = asked;
      } else {
        body = route.body;
        status = route.status ?? 200;
      }
      return new Response(JSON.stringify(body), {
        status,
        headers: { "content-type": "application/json" },
      });
    }),
  );
  return calls;
}

function open(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(
    <QueryClientProvider client={makeQueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}

beforeEach(async () => {
  useUi.setState({ theme: "dark", language: "en", projectId: null });
  await i18n.changeLanguage("en");
});
afterEach(() => vi.unstubAllGlobals());

describe("Projects (FR-001-FR-006)", () => {
  it("lists projects with counts and Claude's drafts, and opens a project", async () => {
    const user = userEvent.setup();
    stub();
    const router = open("/projects");
    const table = await screen.findByRole("table");
    const row = within(table).getByRole("row", { name: /Exerzio/ });
    expect(await within(row).findByText("3 / 7")).toBeVisible();
    expect(within(row).getByText("2")).toBeVisible();
    expect(await screen.findByRole("link", { name: "Stretch" })).toHaveAttribute(
      "href",
      "/projects/new?draft=d1",
    );
    await user.click(within(row).getByRole("button", { name: "Open" }));
    expect(useUi.getState().projectId).toBe("p1");
    expect(router.state.location.pathname).toBe("/");
  });
});

describe("New project (FR-001, FR-008)", () => {
  it("creates a project once the schema check passes", async () => {
    const user = userEvent.setup();
    const calls = stub();
    const router = open("/projects/new");
    const create = await screen.findByRole("button", { name: "Create project" });
    expect(create).toBeDisabled();
    await user.type(screen.getByRole("textbox", { name: "Name" }), "Łydki");
    await user.click(screen.getByRole("button", { name: "Add category" }));
    await user.type(screen.getByRole("textbox", { name: "Category 1 name" }), "Ćwiczenia łydek");
    expect(screen.getByRole("textbox", { name: "Category 1 slug" })).toHaveValue("cwiczenia-lydek");
    await waitFor(() => expect(create).toBeEnabled(), { timeout: 3000 });
    expect(screen.getByText("The configuration passes the schema check.")).toBeVisible();
    await user.click(create);
    await waitFor(() => expect(router.state.location.pathname).toBe("/projects/p2"));
    const post = calls.find((c) => c.method === "POST" && c.path === "/api/v1/projects");
    expect(post?.body).toMatchObject({
      name: "Łydki",
      categories: [{ slug: "cwiczenia-lydek", name: "Ćwiczenia łydek" }],
    });
    expect(useUi.getState().projectId).toBe("p2");
  });

  it("shows Claude's draft with its assumptions; the user confirms it (RULE-010)", async () => {
    const user = userEvent.setup();
    const calls = stub();
    open("/projects/new?draft=d1");
    expect(await screen.findByText("Stretching illustrations")).toBeVisible();
    expect(screen.getByText("flat vector")).toBeVisible();
    expect(screen.getByText("brand colours")).toBeVisible();
    await waitFor(() =>
      expect(screen.getByRole("textbox", { name: "Name" })).toHaveValue("Stretch"),
    );
    const create = screen.getByRole("button", { name: "Create project" });
    await waitFor(() => expect(create).toBeEnabled(), { timeout: 3000 });
    await user.click(create);
    await waitFor(() =>
      expect(
        calls.find((c) => c.path === "/api/v1/projects/drafts/d1/confirm")?.body,
      ).toMatchObject({ config: { name: "Stretch" } }),
    );
  });
});

describe("Project settings (FR-002, FR-007, RULE-005)", () => {
  it("asks before a breaking change and then saves with the acknowledgement", async () => {
    const user = userEvent.setup();
    const puts: { acknowledge_breaking: boolean }[] = [];
    stub({
      "PUT /api/v1/projects/p1/config": async (r) => {
        const body = (await r.clone().json()) as { acknowledge_breaking: boolean };
        puts.push(body);
        return body.acknowledge_breaking
          ? { ...project, current_config_version: 3, config }
          : {
              __status: 409,
              status: 409,
              code: "CONFIG_BREAKING_CHANGE",
              detail: "Confirm",
              changes: ["naming pattern changed"],
            };
      },
    });
    open("/projects/p1");
    const naming = await screen.findByRole("textbox", { name: "File naming" });
    await user.clear(naming);
    await user.type(naming, "{{asset}");
    const save = screen.getByRole("button", { name: "Save as new version" });
    await waitFor(() => expect(save).toBeEnabled(), { timeout: 3000 });
    await user.click(save);
    expect(await screen.findByText("naming pattern changed")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Save anyway" }));
    await waitFor(() => expect(puts).toHaveLength(2));
    expect(puts[1]).toMatchObject({ acknowledge_breaking: true, config: { naming: "{asset}" } });
  });

  it("lets the user allow Claude to decide and compares configuration versions", async () => {
    const user = userEvent.setup();
    const calls = stub();
    open("/projects/p1");
    await user.click(
      await screen.findByRole("checkbox", {
        name: "Claude may approve, reject and publish in this project",
      }),
    );
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ mcp_can_decide: true }),
    );
    await user.click(await screen.findByRole("button", { name: "Compare" }));
    expect(screen.getByText("v1 compared with the current v2")).toBeVisible();
    expect(screen.getByRole("rowheader", { name: "naming" })).toBeVisible();
  });
});

describe("slugify", () => {
  it("handles Polish letters", () => {
    expect(slugify("Żółć łydek – Ćwiczenia")).toBe("zolc-lydek-cwiczenia");
  });
});
