/** Export and publish: what to publish, a preset, a target, the planned files with overwrite
 * flags, and publishing with an explicit confirmation of each overwrite
 * (WP-11: FR-090-FR-095, RULE-004, DD-006, DD-008). */
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router";

import { ApiError } from "../api/client";
import { useJobSet } from "../api/generation";
import {
  FORMATS,
  NEW_PRESET,
  useCreateTarget,
  useExportRoots,
  usePlan,
  usePresets,
  usePublications,
  usePublish,
  usePublishable,
  useSavePreset,
  useTargets,
  type Plan,
  type Preset,
  type PresetDefinition,
  type Source,
} from "../api/publishing";
import { useCollections, type QueueVersion } from "../api/review";
import { useUi } from "../app/store";
import { NeedsProject, ProblemText } from "./common";
import { JOB_CLASS } from "./GenerationStudio";
import r from "./review.module.css";
import s from "./workspace.module.css";

export function Publish() {
  const projectId = useUi((u) => u.projectId);
  if (!projectId) return <NeedsProject module="publish" />;
  return <PublishScreen key={projectId} projectId={projectId} />;
}

type SourceKind = Source["kind"];

function PublishScreen({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const [kind, setKind] = useState<SourceKind>("versions");
  const [chosen, setChosen] = useState<string[]>(() =>
    (params.get("versions") ?? "").split(",").filter(Boolean),
  );
  const [collectionId, setCollectionId] = useState("");
  const [presetId, setPresetId] = useState("");
  const [targetId, setTargetId] = useState("");
  const [plan, setPlan] = useState<Plan | null>(null);
  const [confirmed, setConfirmed] = useState<string[]>([]);
  const [jobId, setJobId] = useState<string | null>(null);

  const publishable = usePublishable(projectId);
  const collections = useCollections(projectId);
  const presets = usePresets(projectId);
  const targets = useTargets(projectId);
  const planner = usePlan();
  const publisher = usePublish();

  const preset = (presets.data ?? []).find((p) => p.id === presetId) ?? presets.data?.[0];
  const target = (targets.data ?? []).find((x) => x.id === targetId) ?? targets.data?.[0];
  let source: Source | null = null;
  if (kind === "versions" && chosen.length) source = { kind, versionIds: chosen };
  if (kind === "collection" && collectionId) source = { kind, collectionId };
  if (kind === "project") source = { kind };
  // Any change makes the shown plan stale.
  const reset = () => {
    setPlan(null);
    setConfirmed([]);
    setJobId(null);
  };
  const why = !source
    ? t("publish.chooseSource")
    : !preset
      ? t("publish.needPreset")
      : !target
        ? t("publish.needTarget")
        : !target.available
          ? t("publish.targetUnavailable")
          : null;
  const pending = plan ? plan.overwrites.filter((p) => !confirmed.includes(p)) : [];

  return (
    <section className={s.stack} aria-label={t("nav.publish")}>
      <div className={r.split}>
        <div className={s.stack}>
          <div className={`panel ${s.column}`}>
            <h2 className="h-panel" style={{ margin: 0 }}>
              {t("publish.what")}
            </h2>
            <div className={s.row} role="radiogroup" aria-label={t("publish.what")}>
              {(["versions", "collection", "project"] as const).map((k) => (
                <label key={k} className={s.radio}>
                  <input
                    type="radio"
                    name="source"
                    checked={kind === k}
                    onChange={() => {
                      setKind(k);
                      reset();
                    }}
                  />
                  {t(`publish.sources.${k}`)}
                </label>
              ))}
            </div>
            {kind === "versions" && (
              <VersionPicker
                rows={publishable.data ?? []}
                loading={publishable.isPending}
                chosen={chosen}
                onChange={(ids) => {
                  setChosen(ids);
                  reset();
                }}
              />
            )}
            {kind === "collection" && (
              <select
                className="input"
                value={collectionId}
                aria-label={t("library.collection")}
                onChange={(e) => {
                  setCollectionId(e.target.value);
                  reset();
                }}
              >
                <option value="">{t("library.chooseCollection")}</option>
                {(collections.data ?? []).map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} ({c.asset_count})
                  </option>
                ))}
              </select>
            )}
            {kind !== "versions" && (
              <p className="muted" style={{ margin: 0, fontSize: 12 }}>
                {t("publish.newestApproved")}
              </p>
            )}
          </div>

          {plan && (
            <PlanTable
              plan={plan}
              confirmed={confirmed}
              onConfirm={setConfirmed}
              locked={!!jobId}
            />
          )}
          {jobId && <PublishJob jobId={jobId} />}
        </div>

        <aside className={s.stack}>
          <PresetPanel
            projectId={projectId}
            presets={presets.data ?? []}
            current={preset}
            onPick={(id) => {
              setPresetId(id);
              reset();
            }}
          />
          <TargetPanel
            projectId={projectId}
            current={target?.id}
            onPick={(id) => {
              setTargetId(id);
              reset();
            }}
          />
          <div className={`panel ${s.column}`}>
            <button
              type="button"
              className="btn"
              disabled={!!why || planner.isPending}
              onClick={() => {
                if (!source || !preset || !target) return;
                planner.mutate(
                  { projectId, presetId: preset.id, targetId: target.id, source },
                  {
                    onSuccess: (p) => {
                      setPlan(p);
                      setConfirmed([]);
                      setJobId(null);
                    },
                  },
                );
              }}
            >
              {t("publish.planFiles")}
            </button>
            {why && (
              <p className="muted" style={{ margin: 0, fontSize: 12 }}>
                {why}
              </p>
            )}
            <button
              type="button"
              className="btn primary"
              disabled={!plan || pending.length > 0 || !!jobId || publisher.isPending}
              onClick={() => {
                if (!plan) return;
                publisher.mutate(
                  { planId: plan.id, confirm: confirmed },
                  { onSuccess: (job) => setJobId(job.id) },
                );
              }}
            >
              {plan ? t("publish.publishN", { count: plan.items.length }) : t("publish.publish")}
            </button>
            {!plan && !why && (
              <p className="muted" style={{ margin: 0, fontSize: 12 }}>
                {t("publish.planFirst")}
              </p>
            )}
            {plan && pending.length > 0 && (
              <p role="status" className={s.error} style={{ fontSize: 12 }}>
                {t("publish.confirmFirst", { count: pending.length })}
              </p>
            )}
            <ProblemText error={planner.error ?? publisher.error} />
          </div>
        </aside>
      </div>
      <History projectId={projectId} />
    </section>
  );
}

function VersionPicker({
  rows,
  loading,
  chosen,
  onChange,
}: {
  rows: QueueVersion[];
  loading: boolean;
  chosen: string[];
  onChange: (ids: string[]) => void;
}) {
  const { t } = useTranslation();
  if (loading) {
    return (
      <p role="status" className="muted">
        {t("inputs.loading")}
      </p>
    );
  }
  if (!rows.length) {
    return (
      <p className="muted" style={{ margin: 0 }}>
        {t("publish.noneApproved")} <Link to="/review">{t("nav.review")}</Link>
      </p>
    );
  }
  const all = rows.every((v) => chosen.includes(v.id));
  return (
    <div className={s.field}>
      <label className={s.radio}>
        <input
          type="checkbox"
          checked={all}
          onChange={() => onChange(all ? [] : rows.map((v) => v.id))}
        />
        {t("publish.all", { count: rows.length })}
      </label>
      <ul className={r.versions} style={{ maxHeight: 320, overflowY: "auto" }}>
        {rows.map((v) => (
          <li key={v.id}>
            <label className={s.radio}>
              <input
                type="checkbox"
                checked={chosen.includes(v.id)}
                onChange={(e) =>
                  onChange(
                    e.target.checked ? [...chosen, v.id] : chosen.filter((id) => id !== v.id),
                  )
                }
              />
              {v.asset.name} <span className="mono muted">v{v.number}</span>
              <span className="muted" style={{ fontSize: 12 }}>
                {t(`versionStates.${v.state}`)}
              </span>
            </label>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** FR-090: format, sizes, naming, folders, optimisation, metadata. */
function PresetPanel({
  projectId,
  presets,
  current,
  onPick,
}: {
  projectId: string;
  presets: Preset[];
  current: Preset | undefined;
  onPick: (id: string) => void;
}) {
  const { t } = useTranslation();
  const [editing, setEditing] = useState<Preset | "new" | null>(null);
  return (
    <div className={`panel ${s.column}`}>
      <div className={s.header}>
        <h2 className="h-panel" style={{ margin: 0 }}>
          {t("publish.preset")}
        </h2>
        <div className={s.actions}>
          {current && (
            <button type="button" className="btn ghost" onClick={() => setEditing(current)}>
              {t("publish.edit")}
            </button>
          )}
          <button type="button" className="btn ghost" onClick={() => setEditing("new")}>
            {t("publish.new")}
          </button>
        </div>
      </div>
      {presets.length > 0 && (
        <select
          className="input"
          value={current?.id ?? ""}
          aria-label={t("publish.preset")}
          onChange={(e) => onPick(e.target.value)}
        >
          {presets.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      )}
      {!presets.length && editing === null && (
        <p className="muted" style={{ margin: 0 }}>
          {t("publish.noPresets")}
        </p>
      )}
      {current && editing === null && <PresetSummary definition={current.definition} />}
      {editing && (
        <PresetForm
          key={editing === "new" ? "new" : editing.id}
          projectId={projectId}
          preset={editing === "new" ? null : editing}
          onDone={(id) => {
            setEditing(null);
            if (id) onPick(id);
          }}
        />
      )}
    </div>
  );
}

function PresetSummary({ definition: d }: { definition: PresetDefinition }) {
  const { t } = useTranslation();
  const sizes = (d.sizes ?? []).map((z) => `${z.width}×${z.height}`).join(", ");
  return (
    <dl className={s.facts} style={{ fontSize: 13 }}>
      <dt>{t("publish.format")}</dt>
      <dd className="mono">{d.format}</dd>
      <dt>{t("publish.sizes")}</dt>
      <dd className="mono">{sizes}</dd>
      <dt>{t("publish.naming")}</dt>
      <dd className="mono">
        {d.folders ? `${d.folders}/` : ""}
        {d.naming}
      </dd>
    </dl>
  );
}

function PresetForm({
  projectId,
  preset,
  onDone,
}: {
  projectId: string;
  preset: Preset | null;
  onDone: (id?: string) => void;
}) {
  const { t } = useTranslation();
  const save = useSavePreset(projectId);
  const [name, setName] = useState(preset?.name ?? "");
  const [d, setD] = useState<PresetDefinition>(preset?.definition ?? NEW_PRESET);
  const sizes = d.sizes ?? [];
  const set = <K extends keyof PresetDefinition>(key: K, value: PresetDefinition[K]) =>
    setD((x) => ({ ...x, [key]: value }));
  const setSize = (i: number, key: "suffix" | "width" | "height", value: string) =>
    set(
      "sizes",
      sizes.map((z, j) =>
        j === i ? { ...z, [key]: key === "suffix" ? value : Number(value) || 0 } : z,
      ),
    );

  return (
    <form
      className={s.form}
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(
          { id: preset?.id, name: name.trim(), definition: d },
          { onSuccess: (p) => onDone(p.id) },
        );
      }}
    >
      <label className={s.field}>
        <span>{t("publish.presetName")}</span>
        <input
          className="input"
          value={name}
          maxLength={120}
          required
          onChange={(e) => setName(e.target.value)}
        />
      </label>
      <div className={s.pair}>
        <label className={s.field}>
          <span>{t("publish.format")}</span>
          <select
            className="input"
            value={d.format}
            onChange={(e) => set("format", e.target.value as PresetDefinition["format"])}
          >
            {FORMATS.map((f) => (
              <option key={f} value={f}>
                {f.toUpperCase()}
              </option>
            ))}
          </select>
        </label>
        <label className={s.field}>
          <span>{t("publish.quality")}</span>
          <input
            className="input"
            type="number"
            min={50}
            max={100}
            value={d.quality}
            onChange={(e) => set("quality", Number(e.target.value))}
          />
        </label>
      </div>
      <fieldset className={s.fieldset}>
        <legend>{t("publish.sizes")}</legend>
        {sizes.map((z, i) => (
          <div key={i} className={s.row}>
            <input
              className="input"
              style={{ width: 90 }}
              value={z.suffix ?? ""}
              placeholder={t("publish.suffix")}
              aria-label={t("publish.suffixN", { n: i + 1 })}
              onChange={(e) => setSize(i, "suffix", e.target.value)}
            />
            <input
              className="input"
              style={{ width: 90 }}
              type="number"
              min={16}
              max={4096}
              value={z.width}
              aria-label={t("publish.widthN", { n: i + 1 })}
              onChange={(e) => setSize(i, "width", e.target.value)}
            />
            ×
            <input
              className="input"
              style={{ width: 90 }}
              type="number"
              min={16}
              max={4096}
              value={z.height}
              aria-label={t("publish.heightN", { n: i + 1 })}
              onChange={(e) => setSize(i, "height", e.target.value)}
            />
            {sizes.length > 1 && (
              <button
                type="button"
                className="btn ghost"
                aria-label={t("publish.removeSize", { n: i + 1 })}
                onClick={() =>
                  set(
                    "sizes",
                    sizes.filter((_, j) => j !== i),
                  )
                }
              >
                ×
              </button>
            )}
          </div>
        ))}
        {sizes.length < 10 && (
          <button
            type="button"
            className="btn ghost"
            style={{ justifySelf: "start" }}
            onClick={() =>
              set("sizes", [...sizes, { suffix: `s${sizes.length + 1}`, width: 512, height: 512 }])
            }
          >
            {t("publish.addSize")}
          </button>
        )}
      </fieldset>
      <label className={s.field}>
        <span>{t("publish.naming")}</span>
        <input
          className="input mono"
          value={d.naming}
          maxLength={200}
          onChange={(e) => set("naming", e.target.value)}
        />
        <span className="muted" style={{ fontSize: 12 }}>
          {t("publish.namingHint")}
        </span>
      </label>
      <label className={s.field}>
        <span>{t("publish.folders")}</span>
        <input
          className="input mono"
          value={d.folders}
          maxLength={200}
          placeholder="{category}"
          onChange={(e) => set("folders", e.target.value)}
        />
      </label>
      <div className={s.pair}>
        <label className={s.field}>
          <span>{t("publish.background")}</span>
          <select
            className="input"
            value={d.background}
            onChange={(e) => set("background", e.target.value as PresetDefinition["background"])}
          >
            <option value="keep">{t("publish.backgrounds.keep")}</option>
            <option value="white">{t("publish.backgrounds.white")}</option>
          </select>
        </label>
        <label className={s.field}>
          <span>{t("publish.resize")}</span>
          <select
            className="input"
            value={d.resize}
            onChange={(e) => set("resize", e.target.value as PresetDefinition["resize"])}
          >
            <option value="contain">{t("publish.resizes.contain")}</option>
            <option value="cover">{t("publish.resizes.cover")}</option>
          </select>
        </label>
      </div>
      <label className={s.radio}>
        <input
          type="checkbox"
          checked={d.optimize}
          onChange={(e) => set("optimize", e.target.checked)}
        />
        {t("publish.optimize")}
      </label>
      <label className={s.radio}>
        <input
          type="checkbox"
          checked={d.metadata === "sidecar"}
          onChange={(e) => set("metadata", e.target.checked ? "sidecar" : "none")}
        />
        {t("publish.sidecar")}
      </label>
      <div className={s.actions}>
        <button type="submit" className="btn primary" disabled={!name.trim() || save.isPending}>
          {t("publish.savePreset")}
        </button>
        <button type="button" className="btn ghost" onClick={() => onDone()}>
          {t("review.cancel")}
        </button>
      </div>
      <ProblemText error={save.error} />
      {save.error instanceof ApiError && Array.isArray(save.error.problem.errors) && (
        <ul className={s.error} style={{ fontSize: 12, margin: 0 }}>
          {(save.error.problem.errors as { msg?: string }[]).map((e, i) => (
            <li key={i}>{e.msg}</li>
          ))}
        </ul>
      )}
    </form>
  );
}

/** FR-091: a folder under one of the configured export roots (ADR-013). */
function TargetPanel({
  projectId,
  current,
  onPick,
}: {
  projectId: string;
  current: string | undefined;
  onPick: (id: string) => void;
}) {
  const { t } = useTranslation();
  const roots = useExportRoots();
  const targets = useTargets(projectId);
  const create = useCreateTarget(projectId);
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [rootId, setRootId] = useState("");
  const [subdir, setSubdir] = useState("");
  const rows = targets.data ?? [];
  const rootList = roots.data ?? [];
  const chosenRoot = rootId || rootList[0]?.id || "";
  return (
    <div className={`panel ${s.column}`}>
      <div className={s.header}>
        <h2 className="h-panel" style={{ margin: 0 }}>
          {t("publish.target")}
        </h2>
        <button
          type="button"
          className="btn ghost"
          disabled={!rootList.length}
          onClick={() => setAdding((a) => !a)}
        >
          {t("publish.new")}
        </button>
      </div>
      {!roots.isPending && !rootList.length && (
        <p className="muted" style={{ margin: 0, fontSize: 12 }}>
          {t("publish.noRoots")}
        </p>
      )}
      {rows.length > 0 && (
        <select
          className="input"
          value={current ?? ""}
          aria-label={t("publish.target")}
          onChange={(e) => onPick(e.target.value)}
        >
          {rows.map((x) => (
            <option key={x.id} value={x.id}>
              {x.name} — {x.root_name ?? "?"}/{x.subdir}
            </option>
          ))}
        </select>
      )}
      {adding && (
        <form
          className={s.form}
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate(
              { name: name.trim(), root_id: chosenRoot, subdir: subdir.trim() },
              {
                onSuccess: (x) => {
                  setAdding(false);
                  setName("");
                  setSubdir("");
                  onPick(x.id);
                },
              },
            );
          }}
        >
          <label className={s.field}>
            <span>{t("publish.targetName")}</span>
            <input
              className="input"
              value={name}
              maxLength={120}
              required
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <div className={s.pair}>
            <label className={s.field}>
              <span>{t("publish.root")}</span>
              <select
                className="input"
                value={chosenRoot}
                onChange={(e) => setRootId(e.target.value)}
              >
                {rootList.map((x) => (
                  <option key={x.id} value={x.id}>
                    {x.name}
                  </option>
                ))}
              </select>
            </label>
            <label className={s.field}>
              <span>{t("publish.subdir")}</span>
              <input
                className="input mono"
                value={subdir}
                maxLength={300}
                placeholder="app/images"
                onChange={(e) => setSubdir(e.target.value)}
              />
            </label>
          </div>
          <div className={s.actions}>
            <button type="submit" className="btn" disabled={!name.trim() || create.isPending}>
              {t("publish.addTarget")}
            </button>
          </div>
          <ProblemText error={create.error} />
        </form>
      )}
    </div>
  );
}

/** DD-006: the planned files; each existing one needs its own confirmation (RULE-004). */
function PlanTable({
  plan,
  confirmed,
  onConfirm,
  locked,
}: {
  plan: Plan;
  confirmed: string[];
  onConfirm: (paths: string[]) => void;
  locked: boolean;
}) {
  const { t } = useTranslation();
  const overwrites = plan.overwrites;
  const all = overwrites.length > 0 && overwrites.every((p) => confirmed.includes(p));
  return (
    <div className={`panel ${s.column}`}>
      <div className={s.header}>
        <h2 className="h-panel" style={{ margin: 0 }}>
          {t("publish.plan", { files: plan.files, versions: plan.items.length })}
        </h2>
        {overwrites.length > 0 && (
          <label className={s.radio}>
            <input
              type="checkbox"
              checked={all}
              disabled={locked}
              onChange={() => onConfirm(all ? [] : overwrites)}
            />
            {t("publish.confirmAll", { count: overwrites.length })}
          </label>
        )}
      </div>
      {overwrites.length > 0 && (
        <p role="alert" className={s.error} style={{ fontSize: 13 }}>
          {t("publish.overwriteWarning", { count: overwrites.length })}
        </p>
      )}
      <div className={s.tableWrap}>
        <table className={s.table}>
          <thead>
            <tr>
              <th scope="col">{t("publish.version")}</th>
              <th scope="col">{t("publish.file")}</th>
              <th scope="col">{t("publish.status")}</th>
            </tr>
          </thead>
          <tbody>
            {plan.items.flatMap((item) =>
              item.files.map((f) => (
                <tr key={f.path}>
                  <td>
                    {item.asset} <span className="mono muted">v{item.number}</span>
                  </td>
                  <td className="mono" style={{ overflowWrap: "anywhere" }}>
                    {f.path}
                  </td>
                  <td>
                    {f.exists ? (
                      <label className={s.radio} style={{ color: "var(--st-rejected)" }}>
                        <input
                          type="checkbox"
                          checked={confirmed.includes(f.path)}
                          disabled={locked}
                          aria-label={t("publish.confirmPath", { path: f.path })}
                          onChange={(e) =>
                            onConfirm(
                              e.target.checked
                                ? [...confirmed, f.path]
                                : confirmed.filter((p) => p !== f.path),
                            )
                          }
                        />
                        {t("publish.overwrites")}
                      </label>
                    ) : (
                      <span className="muted">{t("publish.newFile")}</span>
                    )}
                  </td>
                </tr>
              )),
            )}
          </tbody>
        </table>
      </div>
      {plan.skipped.length > 0 && (
        <details>
          <summary className="muted">
            {t("publish.skipped", { count: plan.skipped.length })}
          </summary>
          <ul className={r.trail}>
            {plan.skipped.map((x, i) => {
              const item = x as { asset?: string; number?: number; reason?: string };
              return (
                <li key={i}>
                  {item.asset} {item.number != null && `v${item.number}`} ·{" "}
                  {t(`publish.reasons.${item.reason ?? ""}`, { defaultValue: item.reason })}
                </li>
              );
            })}
          </ul>
        </details>
      )}
    </div>
  );
}

function PublishJob({ jobId }: { jobId: string }) {
  const { t } = useTranslation();
  const jobs = useJobSet([jobId]);
  const job = jobs.data?.[0];
  if (!job) {
    return (
      <p role="status" className="muted">
        {t("inputs.loading")}
      </p>
    );
  }
  const result = job.result as {
    published?: unknown[];
    failed?: { asset: string; code: string; message: string }[];
  };
  const progress = job.progress as { step?: number; of?: number };
  const error = job.error as { code?: string; message?: string } | null;
  return (
    <div className={`panel ${s.column}`} role="status">
      <div className={s.row}>
        <span className={`badge ${JOB_CLASS[job.state] ?? ""}`}>
          <i />
          {t(`jobStates.${job.state}`)}
        </span>
        {job.state === "running" && progress.of != null && (
          <span className="mono muted">
            {progress.step ?? 0}/{progress.of}
          </span>
        )}
      </div>
      {job.state === "completed" && (
        <p style={{ margin: 0 }}>
          {t("publish.done", { count: result.published?.length ?? 0 })}{" "}
          <Link to="/library">{t("review.openLibrary")}</Link>
        </p>
      )}
      {(result.failed ?? []).map((f, i) => (
        <p key={i} className={s.error} style={{ fontSize: 13 }}>
          {f.asset}: {t(`problems.${f.code}`, { defaultValue: f.message })}
        </p>
      ))}
      {error && (
        <p className={s.error}>
          {t(`problems.${error.code ?? ""}`, { defaultValue: error.message ?? "" })}
        </p>
      )}
    </div>
  );
}

/** FR-093: what was published, where, with which files. */
function History({ projectId }: { projectId: string }) {
  const { t, i18n } = useTranslation();
  const publications = usePublications({ projectId });
  const targets = useTargets(projectId);
  const names = new Map((targets.data ?? []).map((x) => [x.id, x.name]));
  const time = new Intl.DateTimeFormat(i18n.language, { dateStyle: "short", timeStyle: "short" });
  const rows = publications.data ?? [];
  if (!rows.length) return null;
  return (
    <div className={`panel ${s.column}`}>
      <h2 className="h-panel" style={{ margin: 0 }}>
        {t("publish.history")}
      </h2>
      <ul className={r.trail} style={{ maxHeight: 360 }}>
        {rows.map((p) => (
          <li key={p.id}>
            <span className="mono muted">{time.format(new Date(p.at))}</span> ·{" "}
            {names.get(p.target_id) ?? "?"} ·{" "}
            <span className="mono">{(p.files ?? []).map((f) => f.relative_path).join(", ")}</span>
            {(p.files ?? []).some((f) => f.overwrote_sha256) && (
              <span className="muted"> · {t("publish.overwrote")}</span>
            )}
            <span className="muted">
              {" "}
              · {t(`asset.actors.${p.actor}`, { defaultValue: p.actor })}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
