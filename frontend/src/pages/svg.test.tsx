/** SVG Studio (WP-14, UXQ-01: FR-045-FR-047, UC-014). */
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";

import { makeQueryClient } from "../api/queries";
import { svgDataUrl } from "../api/svg";
import { routes } from "../app/routes";
import { useUi } from "../app/store";
import i18n from "../i18n";

type Handler = (request: Request) => unknown;
type Reply = { status?: number; body: unknown };
type Spec = { template_id: string; params: Record<string, unknown>; style_id?: string | null };

const param = (name: string, kind: string, value: string | number, more: object = {}) => ({
  name,
  kind,
  default: value,
  min: null,
  max: null,
  step: null,
  options: [],
  ...more,
});
const templates = [
  {
    id: "icon-line",
    version: 1,
    name: "Icon — rounded line",
    description: "One glyph in a rounded line style.",
    params: [
      param("glyph", "glyph", "dumbbell", { options: ["dumbbell", "heart"] }),
      param("color", "color", "#1f2a44"),
      param("stroke_width", "number", 2, { min: 1, max: 3, step: 0.25 }),
    ],
  },
  {
    id: "pattern-dots",
    version: 1,
    name: "Pattern — dot grid",
    description: "A tileable background of dots.",
    params: [param("color", "color", "#1f2a44")],
  },
];
const style = {
  id: "s1",
  project_id: "p1",
  name: "Flat",
  attributes: { palette: ["#1F2A44", "#2bb3a3"] },
  version: 1,
  archived_at: null,
};

function preview(spec: Spec) {
  const params = { glyph: "dumbbell", color: "#1f2a44", stroke_width: 2, ...spec.params };
  const off = !!spec.style_id && !["#1f2a44", "#2bb3a3"].includes(String(params.color));
  return {
    ready: !off,
    problems: off ? [{ code: "PALETTE_MISMATCH", param: "color", detail: "not in palette" }] : [],
    template: { id: spec.template_id, version: 1 },
    params,
    params_hash: "0123456789abcdef",
    svg: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M1 1" stroke="${String(params.color)}" id="${String(params.glyph)}"/></svg>`,
    sha256: "f".repeat(64),
    width: 24,
    height: 24,
    report: { removed_elements: 0, removed_attributes: 0, bytes_in: 120, bytes_out: 120 },
    palette: spec.style_id ? ["#1f2a44", "#2bb3a3"] : [],
  };
}

const job = {
  id: "j1",
  kind: "svg",
  lane: "cpu",
  state: "queued",
  params: {},
  result: {},
  progress: {},
  error: null,
  wait_reason: null,
};

function stub(overrides: Record<string, Reply | Handler> = {}) {
  const table: Record<string, Reply | Handler> = {
    "GET /api/v1/session": { body: { actor: "user" } },
    "GET /api/v1/projects": { body: [{ id: "p1", name: "Exerzio", slug: "e", type: "x" }] },
    "GET /api/v1/projects/p1": {
      body: {
        id: "p1",
        name: "Exerzio",
        config: { categories: [{ slug: "icons", name: "Icons" }] },
      },
    },
    "GET /api/v1/jobs/summary": { body: { lanes: {}, wait_reasons: {}, workers: [] } },
    "GET /api/v1/assets": { body: [] },
    "GET /api/v1/projects/p1/styles": { body: [style] },
    "GET /api/v1/svg/templates": { body: templates },
    "POST /api/v1/svg:preview": async (r) => preview((await r.clone().json()) as Spec),
    "POST /api/v1/svg": { status: 202, body: { asset_id: "a1", job } },
    "GET /api/v1/jobs/j1": { body: job },
    "GET /api/v1/assets/a1/versions": { body: [] },
    ...overrides,
  };
  const calls: { method: string; path: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const request = input instanceof Request ? input : new Request(String(input));
      const url = new URL(request.url);
      const text = request.method !== "GET" ? await request.clone().text() : "";
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

function open() {
  render(
    <QueryClientProvider client={makeQueryClient()}>
      <RouterProvider router={createMemoryRouter(routes, { initialEntries: ["/svg"] })} />
    </QueryClientProvider>,
  );
}

const previews = (calls: ReturnType<typeof stub>) =>
  calls.filter((c) => c.path === "/api/v1/svg:preview").map((c) => c.body as Spec);
const bigPreview = () => screen.getByRole("img", { name: "Preview at 240 px" });

beforeEach(async () => {
  useUi.setState({ theme: "dark", language: "en", projectId: "p1" });
  await i18n.changeLanguage("en");
});
afterEach(() => vi.unstubAllGlobals());

describe("SVG Studio (FR-045-FR-047)", () => {
  it("previews the real output live and creates a version for review", async () => {
    const user = userEvent.setup();
    const calls = stub();
    open();
    await screen.findByRole("img", { name: "Preview at 240 px" });
    expect(screen.getByRole("img", { name: "Preview at 16 px" })).toBeVisible();
    const first = preview({ template_id: "icon-line", params: {} }).svg;
    expect(bigPreview().getAttribute("src")).toBe(svgDataUrl(first));
    expect(screen.getByText(/icon-line v1 · 0123456789abcdef/)).toBeVisible();

    await user.selectOptions(screen.getByRole("combobox", { name: "Glyph" }), "heart");
    await waitFor(() => expect(bigPreview().getAttribute("src")).toContain("heart"));
    expect(previews(calls).at(-1)).toMatchObject({
      template_id: "icon-line",
      params: { glyph: "heart", stroke_width: 2 },
    });

    await user.type(screen.getByRole("textbox", { name: "Name" }), "Heart icon");
    const create = screen.getByRole("button", { name: "Create for review" });
    await waitFor(() => expect(create).toBeEnabled());
    await user.click(create);
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST" && c.path === "/api/v1/svg")?.body).toEqual({
        project_id: "p1",
        template_id: "icon-line",
        params: { glyph: "heart", color: "#1f2a44", stroke_width: 2 },
        style_id: null,
        asset: { category: "icons", name: "Heart icon" },
      }),
    );
    expect(await screen.findByText(/The version appears below/)).toBeVisible();
  });

  it("offers the style's palette and blocks colours outside it", async () => {
    const user = userEvent.setup();
    const calls = stub({
      "POST /api/v1/svg:preview": async (r) => {
        const spec = (await r.clone().json()) as Spec;
        return preview({ ...spec, params: { ...spec.params, color: "#ff0000" } });
      },
    });
    open();
    await screen.findByRole("option", { name: "Flat" });
    await user.selectOptions(screen.getByRole("combobox", { name: "Style" }), "s1");
    expect(await screen.findByRole("button", { name: "#2bb3a3" })).toBeVisible();
    expect(screen.getByRole("button", { name: "#ffffff" })).toBeVisible(); // a neutral
    await waitFor(() => expect(previews(calls).at(-1)?.style_id).toBe("s1"));
    expect(await screen.findByText("This colour is not in the style's palette.")).toBeVisible();
    expect(screen.getByRole("button", { name: "Create for review" })).toBeDisabled();
    expect(screen.getByText("Fix the problems shown next to the preview.")).toBeVisible();
  });

  it("keeps each template's parameters when switching", async () => {
    const user = userEvent.setup();
    const calls = stub();
    open();
    await user.selectOptions(await screen.findByRole("combobox", { name: "Glyph" }), "heart");
    await user.click(screen.getByRole("button", { name: /Pattern — dot grid/ }));
    await waitFor(() => expect(previews(calls).at(-1)?.template_id).toBe("pattern-dots"));
    expect(screen.queryByRole("combobox", { name: "Glyph" })).toBeNull();
    await user.click(screen.getByRole("button", { name: /Icon — rounded line/ }));
    expect(screen.getByRole("combobox", { name: "Glyph" })).toHaveValue("heart");
  });
});
