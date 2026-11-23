/** Models screen (WP-12: FR-080-FR-084, RULE-007, RULE-008). */
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

const MIT = { id: "mit", name: "MIT", commercial_use: "allowed", url: "", notes: "" };
const UNKNOWN = {
  id: "unknown",
  name: "Not stated",
  commercial_use: "unknown",
  url: "",
  notes: "",
};
const base = {
  id: "sdxl-base-1.0",
  name: "SDXL base 1.0",
  kind: "checkpoint",
  family_id: "sdxl",
  licence: MIT,
  file_name: "sd_xl_base_1.0.safetensors",
  source_url: "https://huggingface.co/x/sd_xl_base_1.0.safetensors",
  sha256: "3".repeat(64),
  bytes: 6938078334,
  vram_mb: 6617,
  origin: "catalogue",
  notes: "",
  status: "available",
  file_bytes: null,
  verification: "unverified",
  verified_at: null,
  licence_conflict: false,
  licence_acknowledged: false,
};
const controlLora = {
  ...base,
  id: "control-lora-openpose-sdxl",
  name: "OpenPose Control-LoRA",
  kind: "controlnet",
  licence: UNKNOWN,
  status: "installed",
  verification: "mismatch",
  licence_conflict: true,
};
const local = {
  ...base,
  id: "local-lora-mine",
  name: "mine.safetensors",
  kind: "lora",
  family_id: null,
  licence: UNKNOWN,
  origin: "local",
  source_url: null,
  sha256: null,
  status: "installed",
};

function stub(overrides: Record<string, Reply | Handler> = {}) {
  const routes: Record<string, Reply | Handler> = {
    "GET /api/v1/session": { body: { actor: "user" } },
    "GET /api/v1/projects": { body: [{ id: "p1", name: "Exerzio", slug: "e", type: "x" }] },
    "GET /api/v1/jobs/summary": { body: { lanes: {}, wait_reasons: {}, workers: [] } },
    "GET /api/v1/jobs": { body: [] },
    "GET /api/v1/models": { body: [base, controlLora, local] },
    ...overrides,
  };
  const calls: Request[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const request = input instanceof Request ? input : new Request(String(input));
      calls.push(request.clone());
      const route = routes[`${request.method} ${new URL(request.url).pathname}`];
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

function renderModels() {
  render(
    <QueryClientProvider client={makeQueryClient()}>
      <RouterProvider router={createMemoryRouter(routes, { initialEntries: ["/models"] })} />
    </QueryClientProvider>,
  );
}

beforeEach(async () => {
  useUi.setState({ theme: "dark", language: "en", projectId: "p1" });
  await i18n.changeLanguage("en");
});
afterEach(() => vi.unstubAllGlobals());

const row = async (name: string) =>
  (await screen.findByText(name)).closest("tr") as HTMLTableRowElement;

describe("Models", () => {
  it("lists models with family, licence, size and state (FR-080)", async () => {
    stub();
    renderModels();
    const sdxl = await row("SDXL base 1.0");
    expect(within(sdxl).getByText("6.46 GB")).toBeVisible();
    expect(within(sdxl).getByText("Available")).toBeVisible();
    const lora = await row("OpenPose Control-LoRA");
    expect(within(lora).getByText("Terms not stated")).toBeVisible();
    expect(within(lora).getByText("Checksum differs")).toBeVisible();
    expect(within(lora).getByRole("button", { name: "Download…" })).toBeVisible();
  });

  it("downloads only after the user confirms file, source and size (RULE-008)", async () => {
    const user = userEvent.setup();
    let sent: unknown = null;
    stub({
      "POST /api/v1/models/sdxl-base-1.0:download": async (r) => {
        sent = await r.json();
        return { id: "j1", kind: "download", state: "queued", params: {}, progress: {} };
      },
    });
    renderModels();
    await user.click(within(await row("SDXL base 1.0")).getByRole("button", { name: "Download…" }));
    const dialog = await screen.findByRole("dialog", { name: "Download SDXL base 1.0?" });
    expect(within(dialog).getByText(base.source_url)).toBeVisible();
    expect(sent).toBeNull();
    await user.click(within(dialog).getByRole("button", { name: "Download 6.46 GB" }));
    await waitFor(() =>
      expect(sent).toEqual({
        file_name: base.file_name,
        source_url: base.source_url,
        bytes: base.bytes,
      }),
    );
  });

  it("asks for an explicit, noted confirmation of a licence conflict (RULE-007)", async () => {
    const user = userEvent.setup();
    let sent: unknown = null;
    stub({
      "POST /api/v1/projects/p1/licence-acknowledgements": async (r) => {
        sent = await r.json();
        return {};
      },
    });
    renderModels();
    await user.click(
      within(await row("OpenPose Control-LoRA")).getByRole("button", { name: "Licence warning" }),
    );
    const dialog = await screen.findByRole("dialog");
    const confirm = within(dialog).getByRole("button", { name: "Confirm use" });
    expect(confirm).toBeDisabled();
    await user.type(within(dialog).getByLabelText("Note (optional)"), "client allows it");
    await user.click(within(dialog).getByRole("checkbox"));
    await user.click(confirm);
    await waitFor(() =>
      expect(sent).toEqual({ model_id: "control-lora-openpose-sdxl", note: "client allows it" }),
    );
  });

  it("shows download progress with a cancel button", async () => {
    stub({
      "GET /api/v1/jobs": (r) =>
        new URL(r.url).searchParams.get("kind") === "download"
          ? [
              {
                id: "j1",
                kind: "download",
                state: "running",
                params: { model_id: "sdxl-base-1.0" },
                progress: { state: "downloading", bytes: 3469039167, of: 6938078334 },
              },
            ]
          : [],
    });
    renderModels();
    const sdxl = await row("SDXL base 1.0");
    expect(await within(sdxl).findByText("50% of 6.46 GB")).toBeVisible();
    expect(within(sdxl).getByRole("button", { name: "Cancel" })).toBeVisible();
  });

  it("lets the user set the family of a local file (RULE-015)", async () => {
    const user = userEvent.setup();
    let sent: unknown = null;
    stub({
      "PATCH /api/v1/models/local-lora-mine": async (r) => {
        sent = await r.json();
        return { ...local, family_id: "sdxl" };
      },
    });
    renderModels();
    await user.selectOptions(
      await screen.findByRole("combobox", { name: "Family of mine.safetensors" }),
      "sdxl",
    );
    await waitFor(() => expect(sent).toEqual({ family_id: "sdxl" }));
  });
});
