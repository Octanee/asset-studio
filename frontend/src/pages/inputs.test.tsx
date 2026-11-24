/** Style Studio, References and Poses (WP-07: FR-010-FR-026, AC-011). */
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";

import { makeQueryClient } from "../api/queries";
import i18n from "../i18n";
import { routes } from "../app/routes";
import { useUi } from "../app/store";

type Handler = (request: Request) => unknown;
type Reply = { status?: number; body: unknown };

const P = "p1";
const STANDING = Array.from({ length: 18 }, (_, i) =>
  i < 14 ? [0.3 + (i % 4) * 0.1, 0.1 + i * 0.05, 1] : null,
);
const BUILTIN = {
  id: "b1",
  project_id: null,
  name: "Standing",
  view: "front",
  aspect: 0.75,
  keypoints: STANDING,
  source: "library",
  source_reference_id: null,
  archived_at: null,
  created_at: "2026-11-23T10:00:00Z",
  updated_at: "2026-11-23T10:00:00Z",
};
const REFERENCE = {
  id: "r1",
  project_id: P,
  role: "pose",
  name: "squat.png",
  sha256: "a".repeat(64),
  mime: "image/png",
  width: 600,
  height: 800,
  bytes: 2048,
  archived_at: null,
  created_at: "2026-11-23T10:00:00Z",
};

const BASE: Record<string, Reply | Handler> = {
  "GET /api/v1/session": { body: { actor: "user" } },
  "GET /api/v1/system/health": { body: { status: "ok", version: "0.1.0" } },
  "GET /api/v1/projects": { body: [{ id: P, name: "Exerzio", slug: "exerzio", type: "x" }] },
  "GET /api/v1/jobs/summary": { body: { lanes: {}, wait_reasons: {}, workers: [] } },
  [`GET /api/v1/projects/${P}/styles`]: { body: [] },
  [`GET /api/v1/projects/${P}/characters`]: { body: [] },
  [`GET /api/v1/projects/${P}/references`]: { body: [] },
  "GET /api/v1/poses": { body: [BUILTIN] },
};

function stub(overrides: Record<string, Reply | Handler> = {}) {
  const routes = { ...BASE, ...overrides };
  const calls: Request[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const request = input instanceof Request ? input : new Request(String(input));
      calls.push(request.clone());
      const url = new URL(request.url);
      const route = routes[`${request.method} ${url.pathname}`];
      if (!route) return new Response(JSON.stringify({ code: "NOT_STUBBED" }), { status: 404 });
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

function renderAt(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(
    <QueryClientProvider client={makeQueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}

beforeEach(async () => {
  useUi.setState({ theme: "dark", language: "en", projectId: P });
  await i18n.changeLanguage("en");
});

afterEach(() => vi.unstubAllGlobals());

describe("Style Studio", () => {
  it("asks for a project first", async () => {
    useUi.setState({ projectId: null });
    stub();
    renderAt("/styles");
    expect(await screen.findByText("Choose a project in the top bar first.")).toBeVisible();
  });

  it("creates a style with palette, avoid list and project attributes (FR-010, FR-011)", async () => {
    const user = userEvent.setup();
    let sent: unknown = null;
    stub({
      [`POST /api/v1/projects/${P}/styles`]: async (r) => {
        sent = await r.json();
        return { id: "s1", project_id: P, version: 1, archived_at: null, ...(sent as object) };
      },
    });
    renderAt("/styles");
    await user.click(await screen.findByRole("button", { name: "New style" }));
    const form = screen.getByRole("form", { name: "Style" });
    await user.type(within(form).getByLabelText("Name"), "Flat vector");
    await user.click(within(form).getByRole("button", { name: "Add colour" }));
    await user.type(within(form).getByLabelText("Avoid"), "text{enter}watermark");
    await user.click(within(form).getByRole("button", { name: "Add attribute" }));
    await user.type(within(form).getByLabelText("Attribute name"), "line_weight");
    await user.type(within(form).getByLabelText("Value"), "2 px");
    expect(within(form).getByRole("button", { name: "Test style" })).toBeDisabled();
    await user.click(within(form).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(sent).not.toBeNull());
    expect(sent).toMatchObject({
      name: "Flat vector",
      attributes: {
        palette: ["#808080"],
        avoid: ["text", "watermark"],
        extra: { line_weight: "2 px" },
      },
    });
  });

  it("translates a name clash", async () => {
    const user = userEvent.setup();
    stub({
      [`POST /api/v1/projects/${P}/styles`]: {
        status: 409,
        body: { code: "STYLE_NAME_TAKEN", detail: "A style with this name already exists." },
      },
    });
    useUi.setState({ language: "pl" });
    await i18n.changeLanguage("pl");
    renderAt("/styles");
    await user.click(await screen.findByRole("button", { name: "Nowy styl" }));
    await user.type(screen.getByLabelText("Nazwa"), "Flat");
    await user.click(screen.getByRole("button", { name: "Zapisz" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Styl o tej nazwie już istnieje.");
  });
});

describe("References", () => {
  it("uploads the file itself with its role (FR-025)", async () => {
    const user = userEvent.setup();
    const calls = stub({
      [`POST /api/v1/projects/${P}/references`]: { body: REFERENCE },
    });
    renderAt("/references");
    await user.selectOptions(await screen.findByLabelText("Role for new uploads"), "pose");
    const file = new File([new Uint8Array([137, 80, 78, 71])], "squat.png", { type: "image/png" });
    await user.upload(screen.getByLabelText("Upload images"), file);
    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    const post = calls.find((c) => c.method === "POST");
    const url = new URL(post?.url ?? "");
    expect(Object.fromEntries(url.searchParams)).toEqual({ role: "pose", name: "squat.png" });
    expect(post?.headers.get("content-type")).toBe("image/png");
    expect(new Uint8Array(await (post as Request).arrayBuffer())).toEqual(
      new Uint8Array([137, 80, 78, 71]),
    );
  });

  it("lists failed files with the reason", async () => {
    const user = userEvent.setup({ applyAccept: false });
    stub({
      [`POST /api/v1/projects/${P}/references`]: {
        status: 415,
        body: { code: "MEDIA_TYPE_UNSUPPORTED", detail: "Upload a PNG, JPEG or WebP image." },
      },
    });
    renderAt("/references");
    const file = new File(["<svg/>"], "logo.svg", { type: "image/svg+xml" });
    await user.upload(await screen.findByLabelText("Upload images"), file);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "logo.svg: Upload a PNG, JPEG or WebP image.",
    );
  });

  it("filters by role and changes a role", async () => {
    const user = userEvent.setup();
    let patched: unknown = null;
    stub({
      [`GET /api/v1/projects/${P}/references`]: { body: [REFERENCE] },
      "PATCH /api/v1/references/r1": async (r) => {
        patched = await r.json();
        return { ...REFERENCE, role: "style" };
      },
    });
    renderAt("/references");
    await user.click(await screen.findByRole("button", { name: /^Style\s*0$/ }));
    expect(screen.getByText(/No references with this role yet/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: /^Pose\s*1$/ }));
    await user.click(screen.getByRole("button", { name: /squat\.png/ }));
    await user.selectOptions(screen.getByRole("combobox", { name: "Role" }), "style");
    await waitFor(() => expect(patched).toEqual({ role: "style" }));
  });
});

describe("Poses", () => {
  it("shows the library and keeps built-in poses read-only (FR-020)", async () => {
    stub();
    renderAt("/poses");
    const library = await screen.findByRole("region", { name: "Pose library" });
    expect(await within(library).findByRole("button", { name: /Standing/ })).toBeVisible();
    expect(await screen.findByRole("button", { name: "Save copy to project" })).toBeEnabled();
    expect(screen.getByText(/Built-in poses are read-only/)).toBeVisible();
  });

  it("moves a joint with the keyboard and mirrors the pose (FR-021)", async () => {
    const user = userEvent.setup();
    stub();
    renderAt("/poses");
    const nose = await screen.findByRole("button", { name: "Nose, 30% across, 10% down" });
    nose.focus();
    await user.keyboard("{ArrowRight}{ArrowRight}{Shift>}{ArrowDown}{/Shift}");
    expect(screen.getByRole("button", { name: "Nose, 32% across, 15% down" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Mirror" }));
    expect(screen.getByRole("button", { name: "Nose, 68% across, 15% down" })).toBeVisible();
  });

  it("needs at least four joints before saving", async () => {
    const user = userEvent.setup();
    stub();
    renderAt("/poses");
    await screen.findByRole("button", { name: "Save copy to project" });
    // 14 joints are visible; hide 11 of them.
    const joints = screen
      .getAllByRole("checkbox")
      .filter((box) => (box as HTMLInputElement).checked);
    for (const box of joints.slice(0, 11)) await user.click(box);
    expect(screen.getByRole("button", { name: "Save copy to project" })).toBeDisabled();
    expect(screen.getByText("A pose needs at least 4 visible joints.")).toBeVisible();
  });

  it("detects a pose from a reference, then saves the edited skeleton (AC-011)", async () => {
    const user = userEvent.setup();
    let saved: unknown = null;
    const job = { id: "j1", kind: "detect_pose", lane: "cpu", wait_reason: null, events: [] };
    stub({
      [`GET /api/v1/projects/${P}/references`]: { body: [REFERENCE] },
      "POST /api/v1/poses:detect": { status: 202, body: { ...job, state: "queued" } },
      "GET /api/v1/jobs/j1": {
        body: {
          ...job,
          state: "completed",
          result: { reference_id: "r1", aspect: 0.75, keypoints: STANDING, score: 0.8 },
        },
      },
      [`POST /api/v1/projects/${P}/poses`]: async (r) => {
        saved = await r.json();
        return { ...BUILTIN, id: "n1", project_id: P, source: "detected", ...(saved as object) };
      },
    });
    renderAt("/poses?reference=r1");
    const panel = await screen.findByRole("region", { name: "Detect from image" });
    await user.click(await within(panel).findByRole("button", { name: "Detect from image" }));
    expect(await screen.findByDisplayValue("Detected pose")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(saved).not.toBeNull());
    expect(saved).toMatchObject({ name: "Detected pose", source_reference_id: "r1" });
  });

  it("explains when detection is not installed and offers the manual way", async () => {
    const user = userEvent.setup();
    const job = { id: "j2", kind: "detect_pose", lane: "cpu", wait_reason: null, events: [] };
    stub({
      [`GET /api/v1/projects/${P}/references`]: { body: [REFERENCE] },
      "POST /api/v1/poses:detect": { status: 202, body: { ...job, state: "queued" } },
      "GET /api/v1/jobs/j2": {
        body: {
          ...job,
          state: "failed",
          error: { code: "POSE_DETECTOR_NOT_INSTALLED", message: "not installed" },
        },
      },
    });
    renderAt("/poses?reference=r1");
    const panel = await screen.findByRole("region", { name: "Detect from image" });
    await user.click(await within(panel).findByRole("button", { name: "Detect from image" }));
    expect(await within(panel).findByRole("alert")).toHaveTextContent(
      "Pose detection models are not installed. Install them with the command in the setup guide.",
    );
    expect(within(panel).getByText(/set the pose by hand/)).toBeVisible();
  });
});

describe("Style LoRAs (FR-016, FR-075)", () => {
  it("links a trained LoRA to a style and changes its strength", async () => {
    const user = userEvent.setup();
    const style = {
      id: "s1",
      project_id: P,
      name: "Flat",
      attributes: { palette: [], avoid: [], extra: {} },
      version: 1,
      archived_at: null,
      created_at: "2026-11-24T08:00:00Z",
      updated_at: "2026-11-24T08:00:00Z",
    };
    const lora = {
      model_id: "lora-exz",
      name: "Exerzio woman (SD15 LoRA)",
      family_id: "sd15",
      status: "installed",
      strength: 0.8,
      trigger_word: "exz_woman",
    };
    let links: unknown[] = [];
    const sent: { method: string; body: unknown }[] = [];
    stub({
      [`GET /api/v1/projects/${P}/styles`]: { body: [style] },
      "GET /api/v1/models": {
        body: [
          { id: "lora-exz", name: lora.name, kind: "lora", family_id: "sd15", status: "installed" },
        ],
      },
      "GET /api/v1/styles/s1/loras": () => links,
      "PUT /api/v1/styles/s1/loras/lora-exz": async (r) => {
        const body = (await r.json()) as { strength: number };
        sent.push({ method: "PUT", body });
        links = [{ ...lora, strength: body.strength }];
        return links;
      },
      "DELETE /api/v1/styles/s1/loras/lora-exz": () => {
        sent.push({ method: "DELETE", body: null });
        links = [];
        return links;
      },
    });
    renderAt("/styles");
    await user.click(await screen.findByRole("button", { name: /Flat/ }));
    expect(await screen.findByText("No LoRA is linked.")).toBeVisible();
    await user.selectOptions(screen.getByRole("combobox", { name: "Link LoRA" }), "lora-exz");
    await user.click(screen.getByRole("button", { name: "Link LoRA" }));
    expect(await screen.findByText(/sd15 · exz_woman/)).toBeVisible();
    expect(sent[0]).toEqual({ method: "PUT", body: { strength: 0.8 } });
    const strength = screen.getByRole("spinbutton", { name: `Strength of ${lora.name}` });
    await user.clear(strength);
    await user.type(strength, "0.6");
    await user.tab();
    await waitFor(() => expect(sent[1]).toEqual({ method: "PUT", body: { strength: 0.6 } }));
    await user.click(screen.getByRole("button", { name: "Unlink" }));
    expect(await screen.findByText("No LoRA is linked.")).toBeVisible();
  });
});
