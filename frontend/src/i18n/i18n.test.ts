/** AC-014 (FR-125): every translation key the screens use exists in Polish and English, so
 * switching the language never shows a raw key. Literal keys must resolve (plural keys via
 * their `_one`/`_other` forms); keys built at run time (`t(\`prefix.${x}\`)`) need their
 * prefix to exist in both languages. */
import en from "./en.json";
import pl from "./pl.json";

type Tree = { [key: string]: string | Tree };

const sources = import.meta.glob(["../**/*.{ts,tsx}", "!../**/*.test.{ts,tsx}"], {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

function lookup(tree: Tree, key: string): string | Tree | undefined {
  let node: string | Tree | undefined = tree;
  for (const part of key.split(".")) {
    if (typeof node !== "object" || node === null) return undefined;
    node = node[part];
  }
  return node;
}

function hasKey(tree: Tree, key: string): boolean {
  if (typeof lookup(tree, key) === "string") return true;
  return ["_one", "_other"].every((suffix) => typeof lookup(tree, key + suffix) === "string");
}

const LITERAL = /\bt\(\s*["']([a-zA-Z0-9_.-]+)["']/g;
const DYNAMIC = /\bt\(\s*`([a-zA-Z0-9_.-]+)\.\$\{/g;

function used(pattern: RegExp): Map<string, string[]> {
  const out = new Map<string, string[]>();
  for (const [file, text] of Object.entries(sources)) {
    for (const match of text.matchAll(pattern)) {
      const key = match[1] ?? "";
      out.set(key, [...(out.get(key) ?? []), file]);
    }
  }
  return out;
}

/** Words that are the same in Polish: names, technical terms and loanwords. A new identical
 * value is most likely an untranslated string; add it here only when Polish really uses it. */
const SAME_IN_BOTH = new Set([
  "Asset Studio", "SVG Studio", "Ctrl K", "Polski", "English", "Rendering", "Checkpoint",
  "LoRA", "LoRA 1", "LoRA 2", "ControlNet", "IP-Adapter", "CLIP vision", "Model", "SDXL",
  "SD 1.5", "VRAM ≥ {{gb}} GB", "Asset", "Prompt", "Seed", "Sampler", "Scheduler", "Problem",
  "Workflow", "Studio", "Claude", "system", "Format", "Worker", "viewBox", "Plus", "API", "VAE",
  "CFG", "SVG", "Tag",
]); // prettier-ignore

function flat(tree: Tree, prefix = ""): [string, string][] {
  return Object.entries(tree).flatMap(([k, v]) =>
    typeof v === "string" ? [[prefix + k, v] as [string, string]] : flat(v, `${prefix}${k}.`),
  );
}

describe("translations (AC-014)", () => {
  it("has no English text left in the Polish file", () => {
    const polish = new Map(flat(pl as Tree));
    const same = flat(en as Tree)
      .filter(([key, value]) => polish.get(key) === value && /[a-z]{3}/i.test(value))
      .filter(([, value]) => !SAME_IN_BOTH.has(value))
      .map(([key]) => key);
    expect(same).toEqual([]);
  });

  const literal = used(LITERAL);
  const dynamic = used(DYNAMIC);

  it("finds the keys the screens use", () => {
    expect(Object.keys(sources).length).toBeGreaterThan(30);
    expect(literal.size).toBeGreaterThan(300);
    expect(dynamic.size).toBeGreaterThan(10);
  });

  it.each([
    ["en", en as Tree],
    ["pl", pl as Tree],
  ])("every literal key exists in %s", (_lang, tree) => {
    const missing = [...literal.keys()].filter((key) => !hasKey(tree, key));
    expect(missing).toEqual([]);
  });

  it.each([
    ["en", en as Tree],
    ["pl", pl as Tree],
  ])("every dynamic key prefix exists in %s", (_lang, tree) => {
    const missing = [...dynamic.keys()].filter(
      (prefix) => typeof lookup(tree, prefix) !== "object",
    );
    expect(missing).toEqual([]);
  });
});
