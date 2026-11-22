import { render, screen } from "@testing-library/react";

import en from "../i18n/en.json";
import pl from "../i18n/pl.json";
import { App } from "./App";

function keys(obj: object, prefix = ""): string[] {
  return Object.entries(obj).flatMap(([k, v]) =>
    typeof v === "object" && v !== null ? keys(v, `${prefix}${k}.`) : [`${prefix}${k}`],
  );
}

describe("App", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(new Response("{}", { status: 200 }))),
    );
  });

  it("renders the product name and reports the API as running", async () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: "Asset Studio" })).toBeInTheDocument();
    expect(await screen.findByText(/Running/)).toBeInTheDocument();
  });
});

describe("i18n", () => {
  it("has the same keys in Polish and English (FR-125)", () => {
    expect(keys(pl).sort()).toEqual(keys(en).sort());
  });
});
