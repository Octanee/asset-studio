import { QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";

import { makeQueryClient } from "../api/queries";
import i18n from "../i18n";
import en from "../i18n/en.json";
import pl from "../i18n/pl.json";
import { MODULES } from "./modules";
import { routes } from "./routes";
import { useUi } from "./store";

type Reply = { status?: number; body: unknown };
type Api = Record<string, Reply>;

const DEFAULT_API: Api = {
  "/api/v1/session": { body: { actor: "user" } },
  "/api/v1/system/health": { body: { status: "ok", version: "0.1.0" } },
  "/api/v1/projects": {
    body: [
      { id: "p1", name: "Exerzio illustrations", slug: "exerzio", type: "illustration" },
      { id: "p2", name: "Icons", slug: "icons", type: "icon" },
    ],
  },
  "/api/v1/jobs/summary": {
    body: {
      lanes: { gpu: { running: 1, queued: 4 }, cpu: { queued: 2 } },
      wait_reasons: {},
      workers: [{}],
    },
  },
};

function stubApi(overrides: Api = {}) {
  const api = { ...DEFAULT_API, ...overrides };
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url = new URL(input instanceof Request ? input.url : String(input), "http://localhost");
    const reply = api[url.pathname];
    if (!reply) return Promise.resolve(new Response("{}", { status: 404 }));
    return Promise.resolve(
      new Response(JSON.stringify(reply.body), {
        status: reply.status ?? 200,
        headers: { "content-type": "application/json" },
      }),
    );
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderAt(path = "/") {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(
    <QueryClientProvider client={makeQueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}

function keys(obj: object, prefix = ""): string[] {
  return Object.entries(obj).flatMap(([k, v]) =>
    typeof v === "object" && v !== null ? keys(v, `${prefix}${k}.`) : [`${prefix}${k}`],
  );
}

beforeEach(async () => {
  useUi.setState({ theme: "dark", language: "en", projectId: null });
  await i18n.changeLanguage("en");
});

afterEach(() => vi.unstubAllGlobals());

describe("app shell", () => {
  it("starts a session, then shows the rail with all 14 modules in order", async () => {
    const fetchMock = stubApi();
    renderAt("/");
    const rail = await screen.findByRole("navigation", { name: "Modules" });
    const links = within(rail).getAllByRole("link");
    expect(links.map((l) => l.getAttribute("aria-label"))).toEqual(
      MODULES.map((m) => en.nav[m.id]),
    );
    const first = fetchMock.mock.calls[0]?.[0] as Request;
    expect(new URL(first.url).pathname).toBe("/api/v1/session");
  });

  it("marks the active module and titles the top bar", async () => {
    stubApi();
    renderAt("/workflows");
    const rail = await screen.findByRole("navigation", { name: "Modules" });
    expect(within(rail).getByRole("link", { name: "Workflows" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("heading", { level: 1, name: "Workflows" })).toBeInTheDocument();
    expect(screen.getByText(/arrives in WP-08/)).toBeInTheDocument();
  });

  it("shows live queue counts in the top bar (FR-041)", async () => {
    stubApi();
    renderAt("/");
    const queue = await screen.findByTestId("queue-indicator");
    expect(queue).toHaveAttribute("href", "/queue");
    expect(await within(queue).findByText("1 running")).toBeInTheDocument();
    expect(within(queue).getByText("6 queued")).toBeInTheDocument();
  });

  it("says when no worker is running", async () => {
    stubApi({
      "/api/v1/jobs/summary": {
        body: { lanes: { gpu: { queued: 1 } }, wait_reasons: {}, workers: [] },
      },
    });
    renderAt("/");
    expect(await screen.findByText("Worker offline")).toBeInTheDocument();
  });

  it("switches the language at runtime and remembers it (FR-125)", async () => {
    stubApi();
    renderAt("/library");
    await screen.findByRole("heading", { level: 1, name: "Asset Library" });
    await userEvent.click(screen.getByRole("button", { name: "PL" }));
    expect(
      await screen.findByRole("heading", { level: 1, name: "Biblioteka zasobów" }),
    ).toBeInTheDocument();
    expect(useUi.getState().language).toBe("pl");
    expect(document.documentElement.lang).toBe("pl");
  });

  it("selects a project in the switcher", async () => {
    stubApi();
    renderAt("/");
    const trigger = await screen.findByRole("button", { name: "Switch project" });
    await userEvent.click(trigger);
    await userEvent.click(await screen.findByRole("menuitemradio", { name: /Icons/ }));
    expect(useUi.getState().projectId).toBe("p2");
    expect(await screen.findByText("Icons")).toBeInTheDocument();
  });

  it("opens the command palette with Ctrl K and navigates", async () => {
    stubApi();
    const router = renderAt("/");
    await screen.findByRole("navigation", { name: "Modules" });
    await userEvent.keyboard("{Control>}k{/Control}");
    const input = await screen.findByRole("combobox");
    await userEvent.type(input, "pose");
    await userEvent.keyboard("{Enter}");
    expect(router.state.location.pathname).toBe("/poses");
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("changes the theme from settings", async () => {
    stubApi();
    renderAt("/settings");
    await userEvent.click(await screen.findByRole("radio", { name: "Daylight (light)" }));
    expect(document.documentElement.dataset.theme).toBe("light");
  });

  it("explains a missing setup instead of showing a broken shell", async () => {
    stubApi({
      "/api/v1/session": {
        status: 503,
        body: { code: "NOT_CONFIGURED", detail: "Run setup first: the session secret is missing." },
      },
    });
    renderAt("/");
    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("Asset Studio is not set up yet")).toBeInTheDocument();
    expect(within(alert).getByText(/session secret is missing/)).toBeInTheDocument();
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });

  it("shows a not-found page inside the shell", async () => {
    stubApi();
    renderAt("/nowhere");
    expect(await screen.findByText("Page not found")).toBeInTheDocument();
  });
});

describe("live events", () => {
  it("refreshes the queue when a job event arrives (NFR-003)", async () => {
    const sources: { url: string; listeners: Record<string, () => void> }[] = [];
    class FakeEventSource {
      listeners: Record<string, () => void> = {};
      url: string;
      constructor(url: string) {
        this.url = url;
        sources.push(this);
      }
      addEventListener(type: string, fn: () => void) {
        this.listeners[type] = fn;
      }
      removeEventListener() {}
      close() {}
    }
    const fetchMock = stubApi();
    vi.stubGlobal("EventSource", FakeEventSource);
    renderAt("/");
    await screen.findByText("1 running");
    const summaryCalls = () =>
      fetchMock.mock.calls.filter(
        ([r]) => new URL((r as Request).url).pathname === "/api/v1/jobs/summary",
      ).length;
    const before = summaryCalls();
    expect(sources[0]?.url).toBe("/api/v1/events");
    await act(async () => sources[0]?.listeners.job?.());
    await vi.waitFor(() => expect(summaryCalls()).toBeGreaterThan(before));
  });
});

const ENGINE_UP = {
  provider: "comfyui",
  engine: "comfyui",
  available: true,
  version: "0.46.0",
  reason: null,
  detail: null,
  devices: [{ name: "cuda:0", vram_total_mb: 6144, vram_free_mb: 3072 }],
  features: [],
  agent: { configured: true, reachable: true },
};
const ENGINE_DOWN = {
  ...ENGINE_UP,
  available: false,
  version: null,
  reason: "ENGINE_UNAVAILABLE",
  devices: [],
};

describe("engine (FR-043)", () => {
  it("shows the engine and GPU memory in the top bar", async () => {
    stubApi({ "/api/v1/system/engine": { body: ENGINE_UP } });
    renderAt("/");
    expect(await screen.findByText("ComfyUI · GPU 3.0/6 GB")).toBeInTheDocument();
  });

  it("starts a stopped engine from the system page", async () => {
    const fetchMock = stubApi({
      "/api/v1/system/engine": { body: ENGINE_DOWN },
      "/api/v1/system/engine/start": { body: ENGINE_UP },
    });
    renderAt("/system");
    expect(await screen.findByText(/GPU jobs wait in the queue/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Start engine" }));
    const post = fetchMock.mock.calls.map(([r]) => r as Request).find((r) => r.method === "POST");
    expect(post && new URL(post.url).pathname).toBe("/api/v1/system/engine/start");
    expect(await screen.findByRole("button", { name: "Stop engine" })).toBeInTheDocument();
  });

  it("explains why the engine cannot be started without the host agent (DD-008)", async () => {
    stubApi({
      "/api/v1/system/engine": { body: { ...ENGINE_DOWN, agent: { configured: false } } },
    });
    renderAt("/system");
    const start = await screen.findByRole("button", { name: "Start engine" });
    await vi.waitFor(() => expect(start).toBeDisabled());
    expect(screen.getByText(/host agent is not set up/)).toBeInTheDocument();
  });
});

describe("i18n", () => {
  it("has the same keys in Polish and English (FR-125)", () => {
    expect(keys(pl).sort()).toEqual(keys(en).sort());
  });
});
