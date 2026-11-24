/** SVG Studio (WP-14, UXQ-01: FR-045-FR-047, UC-014): pick a template, set its parameters
 * and see the real output live; creating queues a CPU job whose version goes to review like
 * any other. Colours come from the chosen style's palette. */
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { useAssets, useDebounced, useProject } from "../api/generation";
import { useStyles } from "../api/library";
import {
  svgDataUrl,
  useCreateSvg,
  useSvgPreview,
  useSvgTemplates,
  type SvgParam,
  type SvgParams,
  type SvgPreview,
  type SvgSpec,
  type SvgTemplate,
} from "../api/svg";
import { useUi } from "../app/store";
import { NeedsProject, ProblemText } from "./common";
import { RunningJobs, Versions } from "./GenerationStudio";
import v from "./svg.module.css";
import s from "./workspace.module.css";

const NEUTRALS = ["#ffffff", "#000000"];
const SIZES = [64, 48, 24, 16] as const;
type Background = "transparent" | "light" | "dark";
const BACKGROUNDS: readonly Background[] = ["transparent", "light", "dark"];
// Small stand-ins for the picker; the preview always shows the real output.
const TEMPLATE_ICONS: Record<string, React.ReactNode> = {
  "icon-line": (
    <path
      d="M6 7v10M18 7v10M3 10v4M21 10v4M6 12h12"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
    />
  ),
  "badge-circle": <circle cx={12} cy={12} r={10} fill="currentColor" />,
  "pattern-dots": (
    <g fill="currentColor">
      {[5, 12, 19].flatMap((y) =>
        [5, 12, 19].map((x) => <circle key={`${x}-${y}`} cx={x} cy={y} r={1.6} />),
      )}
    </g>
  ),
};

export interface SvgDraft {
  target: "new" | "existing";
  assetId: string;
  category: string;
  name: string;
  templateId: string;
  styleId: string;
  /** Parameters per template, so switching back keeps what was set. */
  params: Record<string, SvgParams>;
}

export const SVG_START: SvgDraft = {
  target: "new",
  assetId: "",
  category: "",
  name: "",
  templateId: "",
  styleId: "",
  params: {},
};

export function paramsFor(template: SvgTemplate, draft: SvgDraft): SvgParams {
  const defaults = Object.fromEntries(template.params.map((p) => [p.name, p.default]));
  return { ...defaults, ...(draft.params[template.id] ?? {}) };
}

/** The request for the API; `asset` only when a version is to be created. */
export function toSvgSpec(
  draft: SvgDraft,
  projectId: string,
  template: SvgTemplate,
  category: string,
  withAsset: boolean,
): SvgSpec | null {
  const spec: SvgSpec = {
    project_id: projectId,
    template_id: template.id,
    params: paramsFor(template, draft),
    style_id: draft.styleId || null,
  };
  if (!withAsset) return spec;
  if (draft.target === "existing") {
    return draft.assetId ? { ...spec, asset: { asset_id: draft.assetId } } : null;
  }
  if (!category) return null;
  return { ...spec, asset: { category, name: draft.name.trim() || template.name } };
}

export function SvgStudio() {
  const projectId = useUi((u) => u.projectId);
  if (!projectId) return <NeedsProject module="svg" />;
  return <Studio key={projectId} projectId={projectId} />;
}

function Studio({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const templates = useSvgTemplates();
  const project = useProject(projectId);
  const assets = useAssets(projectId);
  const styles = useStyles(projectId);
  const create = useCreateSvg();
  const [draft, setDraft] = useState<SvgDraft>(SVG_START);
  const [background, setBackground] = useState<Background>("transparent");
  const [jobIds, setJobIds] = useState<string[]>([]);
  const set = <K extends keyof SvgDraft>(key: K, value: SvgDraft[K]) =>
    setDraft((d) => ({ ...d, [key]: value }));

  const list = templates.data ?? [];
  const template = list.find((x) => x.id === draft.templateId) ?? list[0];
  const categories = project.data?.config.categories ?? [];
  const category = draft.category || categories[0]?.slug || "";
  const liveStyles = (styles.data ?? []).filter((x) => !x.archived_at);
  const style = liveStyles.find((x) => x.id === draft.styleId);
  const palette = (style?.attributes.palette ?? []).map((c) => c.toLowerCase());
  const params = template ? paramsFor(template, draft) : {};
  const previewSpec = useMemo(
    () => (template ? toSvgSpec(draft, projectId, template, category, false) : null),
    [draft, projectId, template, category],
  );
  const createSpec = template ? toSvgSpec(draft, projectId, template, category, true) : null;
  const preview = useSvgPreview(useDebounced(previewSpec, 150));
  const shown = preview.data;
  const versionsOf = draft.target === "existing" && draft.assetId ? draft.assetId : null;
  const assetName = (assets.data ?? []).find((a) => a.id === versionsOf)?.name;
  const existing = (assets.data ?? []).find((a) => a.id === draft.assetId);

  const setParam = (name: string, value: string | number) => {
    if (!template) return;
    setDraft((d) => ({
      ...d,
      params: { ...d.params, [template.id]: { ...paramsFor(template, d), [name]: value } },
    }));
  };

  // Disabled controls say why (DD-008).
  const blocked = !createSpec
    ? t("svg.incomplete")
    : shown && !shown.ready
      ? t("svg.notReady")
      : null;

  return (
    <div className={s.studio}>
      <form
        className={`panel ${s.column}`}
        aria-label={t("svg.settings")}
        onSubmit={(e) => {
          e.preventDefault();
          if (!createSpec || !shown?.ready) return;
          create.mutate(createSpec, {
            onSuccess: (q) => {
              setJobIds((cur) => [q.job.id, ...cur]);
              // Creating again makes a new version of this asset, not a second asset.
              setDraft((d) => ({ ...d, target: "existing", assetId: q.asset_id }));
            },
          });
        }}
      >
        <fieldset className={s.fieldset}>
          <legend className="label">{t("svg.asset")}</legend>
          <div className={s.row}>
            {(["new", "existing"] as const).map((target) => (
              <label key={target} className={s.radio}>
                <input
                  type="radio"
                  name="svg-target"
                  checked={draft.target === target}
                  onChange={() => set("target", target)}
                />
                {t(`generation.targets.${target}`)}
              </label>
            ))}
          </div>
          {draft.target === "existing" ? (
            <>
              <select
                className="input"
                aria-label={t("svg.asset")}
                value={draft.assetId}
                onChange={(e) => set("assetId", e.target.value)}
              >
                <option value="">{t("generation.chooseAsset")}</option>
                {(assets.data ?? []).map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name} · {a.category}
                  </option>
                ))}
              </select>
              {existing && (
                <span className="muted" style={{ fontSize: 12 }}>
                  {t("generation.newVersion", { n: existing.version_count + 1 })}
                </span>
              )}
            </>
          ) : (
            <div className={s.pair}>
              <label className={s.field}>
                <span className="label">{t("generation.category")}</span>
                <select
                  className="input"
                  value={category}
                  onChange={(e) => set("category", e.target.value)}
                >
                  {categories.map((c) => (
                    <option key={c.slug} value={c.slug}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className={s.field}>
                <span className="label">{t("generation.name")}</span>
                <input
                  className="input"
                  maxLength={200}
                  value={draft.name}
                  placeholder={template?.name}
                  onChange={(e) => set("name", e.target.value)}
                />
              </label>
            </div>
          )}
        </fieldset>

        <fieldset className={s.fieldset}>
          <legend className="label">{t("svg.template")}</legend>
          {templates.isPending && (
            <p role="status" className="muted" style={{ margin: 0 }}>
              {t("inputs.loading")}
            </p>
          )}
          <div className={v.templates}>
            {list.map((x) => (
              <button
                key={x.id}
                type="button"
                className={v.template}
                aria-pressed={x.id === template?.id}
                onClick={() => set("templateId", x.id)}
              >
                <svg
                  viewBox="0 0 24 24"
                  width={32}
                  height={32}
                  aria-hidden="true"
                  className="muted"
                >
                  {TEMPLATE_ICONS[x.id]}
                </svg>
                <span className={s.grow}>
                  <span style={{ display: "block", fontWeight: 500 }}>
                    {t(`svg.templates.${x.id}.name`, { defaultValue: x.name })}
                  </span>
                  <span className="muted" style={{ display: "block", fontSize: 12 }}>
                    {t(`svg.templates.${x.id}.description`, { defaultValue: x.description })}
                  </span>
                </span>
                <span className="mono muted">v{x.version}</span>
              </button>
            ))}
          </div>
        </fieldset>

        <div className={s.field}>
          <label className="label" htmlFor="svg-style">
            {t("generation.style")}
          </label>
          <select
            id="svg-style"
            className="input"
            value={draft.styleId}
            aria-describedby="svg-style-hint"
            onChange={(e) => set("styleId", e.target.value)}
          >
            <option value="">{t("generation.none")}</option>
            {liveStyles.map((x) => (
              <option key={x.id} value={x.id}>
                {x.name}
              </option>
            ))}
          </select>
          <span id="svg-style-hint" className="muted" style={{ fontSize: 12 }}>
            {style && palette.length
              ? t("svg.paletteHint", { name: style.name })
              : t("svg.noPalette")}
          </span>
        </div>

        {template && (
          <fieldset className={s.fieldset}>
            <legend className="label">{t("svg.parameters")}</legend>
            {template.params.map((p) => (
              <ParamField
                key={`${template.id}-${p.name}`}
                param={p}
                value={params[p.name] ?? p.default}
                palette={palette}
                onChange={(value) => setParam(p.name, value)}
              />
            ))}
          </fieldset>
        )}

        <div className={s.submit}>
          <span className="mono muted" style={{ fontSize: 12 }}>
            {t("svg.cpu")}
          </span>
          <button
            type="submit"
            className="btn primary"
            disabled={!createSpec || !shown?.ready || create.isPending}
          >
            {draft.target === "existing" && existing
              ? t("svg.createVersion", { n: existing.version_count + 1 })
              : t("svg.create")}
          </button>
          {blocked && (
            <span className="muted" style={{ fontSize: 12 }}>
              {blocked}
            </span>
          )}
          <ProblemText error={create.error} />
          {create.isSuccess && (
            <p role="status" className="muted" style={{ margin: 0 }}>
              {t("svg.queued")}
            </p>
          )}
        </div>
      </form>

      <div className={s.stack}>
        <div className={v.output}>
          <section className={`panel ${s.column}`} aria-labelledby="svg-preview">
            <div className={s.row} style={{ justifyContent: "space-between" }}>
              <h2 id="svg-preview" className="h-panel">
                {t("svg.preview")}
              </h2>
              <div className={s.tabs} role="group" aria-label={t("svg.background")}>
                {BACKGROUNDS.map((b) => (
                  <button
                    key={b}
                    type="button"
                    className="btn ghost"
                    aria-pressed={background === b}
                    onClick={() => setBackground(b)}
                  >
                    {t(`svg.backgrounds.${b}`)}
                  </button>
                ))}
              </div>
            </div>
            <ProblemText error={preview.error} />
            {shown ? (
              <>
                <div className={`${v.stage} ${v[background]}`}>
                  <img src={svgDataUrl(shown.svg)} alt={t("svg.previewAlt", { size: 240 })} />
                </div>
                <div className={v.sizes}>
                  {SIZES.map((px) => (
                    <div key={px} className={v.size}>
                      <div
                        className={`${v.sizeBox} ${v[background]}`}
                        style={{ width: px + 24, height: px + 24 }}
                      >
                        <img
                          src={svgDataUrl(shown.svg)}
                          width={px}
                          height={px}
                          alt={t("svg.previewAlt", { size: px })}
                        />
                      </div>
                      <span className="mono muted">{px} px</span>
                    </div>
                  ))}
                </div>
                <p className="muted" style={{ margin: 0, fontSize: 12 }}>
                  {t("svg.deterministic")}
                </p>
              </>
            ) : (
              !preview.error && (
                <p role="status" className="muted" style={{ margin: 0 }}>
                  {t("inputs.loading")}
                </p>
              )
            )}
          </section>
          {shown && <Output preview={shown} />}
        </div>
        <RunningJobs ids={jobIds} />
        {versionsOf && <Versions assetId={versionsOf} name={assetName} onQueued={() => {}} />}
      </div>
    </div>
  );
}

function ParamField({
  param,
  value,
  palette,
  onChange,
}: {
  param: SvgParam;
  value: string | number;
  palette: string[];
  onChange: (value: string | number) => void;
}) {
  const { t } = useTranslation();
  const label = t(`svg.params.${param.name}`, { defaultValue: param.name });
  if (param.kind === "glyph") {
    return (
      <label className={s.field}>
        <span className="label">{label}</span>
        <select className="input" value={String(value)} onChange={(e) => onChange(e.target.value)}>
          {param.options.map((o) => (
            <option key={o} value={o}>
              {t(`svg.glyphs.${o}`, { defaultValue: o })}
            </option>
          ))}
        </select>
      </label>
    );
  }
  if (param.kind === "color") {
    const colour = String(value).toLowerCase();
    if (palette.length) {
      const choices = [...palette, ...NEUTRALS.filter((n) => !palette.includes(n))];
      return (
        <div className={s.field}>
          <span className="label" id={`svg-${param.name}`}>
            {label} · <span className="mono">{colour}</span>
          </span>
          <div className={v.swatches} role="group" aria-labelledby={`svg-${param.name}`}>
            {choices.map((c) => (
              <button
                key={c}
                type="button"
                className={v.swatch}
                style={{ background: c }}
                aria-label={c}
                aria-pressed={c === colour}
                onClick={() => onChange(c)}
              />
            ))}
          </div>
        </div>
      );
    }
    return (
      <label className={s.field}>
        <span className="label">
          {label} · <span className="mono">{colour}</span>
        </span>
        <input type="color" value={colour} onChange={(e) => onChange(e.target.value)} />
      </label>
    );
  }
  const n = Number(value);
  return (
    <label className={s.field}>
      <span className="label">
        {label} · <span className="mono">{n}</span>
      </span>
      <input
        type="range"
        min={param.min ?? undefined}
        max={param.max ?? undefined}
        step={param.step ?? undefined}
        value={n}
        onChange={(e) => onChange(e.target.valueAsNumber)}
      />
    </label>
  );
}

function Output({ preview }: { preview: SvgPreview }) {
  const { t } = useTranslation();
  const kb = (bytes: number) => `${(bytes / 1024).toFixed(1)} kB`;
  return (
    <aside className={`panel ${s.column}`} aria-labelledby="svg-output">
      <h2 id="svg-output" className="h-panel">
        {t("svg.output")}
      </h2>
      <ul className={s.checks}>
        <li>
          <span className="badge s-approved">
            <i />
            OK
          </span>{" "}
          {t("svg.sanitised", {
            elements: preview.report.removed_elements,
            attributes: preview.report.removed_attributes,
          })}
        </li>
        <li>
          <span className="badge s-approved">
            <i />
            OK
          </span>{" "}
          {t("svg.optimised")}{" "}
          <span className="mono">
            {kb(preview.report.bytes_in)} → {kb(preview.report.bytes_out)}
          </span>
        </li>
        {preview.problems.map((p) => (
          <li key={p.param}>
            <span className="badge s-failed">
              <i />
              {t("generation.problem")}
            </span>{" "}
            {t(`problems.${p.code}`, { defaultValue: p.detail })}{" "}
            <span className="mono muted">{p.param}</span>
          </li>
        ))}
        {preview.palette.length > 0 && !preview.problems.length && (
          <li>
            <span className="badge s-approved">
              <i />
              OK
            </span>{" "}
            {t("svg.paletteOk")}
          </li>
        )}
      </ul>
      <dl className={s.facts}>
        <dt>{t("svg.fingerprint")}</dt>
        <dd className="mono">
          {preview.template.id} v{preview.template.version} · {preview.params_hash}
        </dd>
        <dt>{t("svg.size")}</dt>
        <dd className="mono">
          {preview.width} × {preview.height}
        </dd>
      </dl>
      <p className="muted" style={{ margin: 0, fontSize: 12 }}>
        {t("svg.exportNote")}
      </p>
      <details>
        <summary className="label" style={{ cursor: "pointer" }}>
          {t("svg.source")}
        </summary>
        <pre className={`mono ${v.source}`}>{preview.svg}</pre>
      </details>
    </aside>
  );
}
