/** Generation Studio: request, checks before queueing, running jobs and versions
 * (WP-08: FR-030-FR-038, FR-052, RULE-007, RULE-013, RULE-015, DD-004, DD-008). */
import type { TFunction } from "i18next";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import {
  ACTIVE,
  randomSeed,
  SAMPLERS,
  SCHEDULERS,
  stepProgress,
  useAssets,
  useDebounced,
  useGenerationCheck,
  useJobAction,
  useJobSet,
  useProject,
  useProcessVersion,
  useQueueGeneration,
  useRegenerate,
  useVersions,
  VARIANT_COUNTS,
  versionFileUrl,
  type Check,
  type GenerationSpec,
  type JobRow,
  type VersionRow,
} from "../api/generation";
import { useCharacters, usePoses, useReferences, useStyles } from "../api/library";
import { useModels } from "../api/models";
import { useUi } from "../app/store";
import { linesOf, NeedsProject, ProblemText } from "./common";
import { PoseThumb } from "./PoseCanvas";
import s from "./workspace.module.css";

export const JOB_CLASS: Record<string, string> = {
  queued: "s-generated",
  running: "s-processing",
  completed: "s-approved",
  failed: "s-failed",
  cancelled: "s-archived",
  interrupted: "s-archived",
};
export const VERSION_CLASS: Record<string, string> = {
  generated: "s-generated",
  processing: "s-processing",
  processing_failed: "s-failed",
  awaiting_review: "s-review",
  approved: "s-approved",
  rejected: "s-rejected",
  published: "s-published",
  archived: "s-archived",
  deleted: "s-archived",
};

export interface Draft {
  mode: "single" | "batch";
  target: "existing" | "new";
  assetId: string;
  category: string;
  name: string;
  items: string;
  styleId: string;
  characterId: string;
  poseId: string;
  poseStrength: number;
  referenceId: string;
  referenceWeight: number;
  initId: string;
  denoise: number;
  prompt: string;
  negative: string;
  variants: number;
  checkpointId: string;
  seed: string;
  steps: number;
  cfg: number;
  sampler: string;
  scheduler: string;
  width: number;
  height: number;
}

export const START: Draft = {
  mode: "single",
  target: "new",
  assetId: "",
  category: "",
  name: "",
  items: "",
  styleId: "",
  characterId: "",
  poseId: "",
  poseStrength: 1,
  referenceId: "",
  referenceWeight: 0.6,
  initId: "",
  denoise: 0.6,
  prompt: "",
  negative: "",
  variants: 1,
  checkpointId: "",
  seed: "",
  steps: 30,
  cfg: 6.5,
  sampler: "dpmpp_2m",
  scheduler: "karras",
  width: 1024,
  height: 1024,
};

/** Batch lines: "name" or "name | extra prompt" (FR-034: one new asset per line). */
export function batchItems(text: string): { name: string; prompt: string }[] {
  return linesOf(text).map((line) => {
    const [head = "", ...rest] = line.split("|");
    const name = head.trim();
    const extra = rest.join("|").trim();
    return { name: name.slice(0, 200), prompt: extra || name };
  });
}

/** The request for the API, or null while something it needs is not chosen yet. */
export function toSpec(d: Draft, projectId: string, category: string): GenerationSpec | null {
  if (!d.checkpointId) return null;
  const items = d.mode === "batch" ? batchItems(d.items).filter((i) => i.name) : [];
  if (d.mode === "batch" && !items.length) return null;
  let asset: GenerationSpec["asset"];
  if (d.mode === "single" && d.target === "existing") {
    if (!d.assetId) return null;
    asset = { asset_id: d.assetId };
  } else {
    if (!category) return null;
    asset = { category, ...(d.mode === "single" && d.name.trim() ? { name: d.name.trim() } : {}) };
  }
  const seed = /^\d+$/.test(d.seed.trim()) ? Number(d.seed.trim()) : null;
  return {
    project_id: projectId,
    asset,
    checkpoint_id: d.checkpointId,
    style_id: d.styleId || null,
    character_id: d.characterId || null,
    pose_id: d.poseId || null,
    pose_strength: d.poseStrength,
    pose_end: 1,
    reference: d.referenceId
      ? { reference_id: d.referenceId, weight: d.referenceWeight, end: 1 }
      : null,
    init: d.initId ? { reference_id: d.initId, denoise: d.denoise } : null,
    prompt: d.prompt,
    negative: d.negative,
    seed,
    steps: d.steps,
    cfg: d.cfg,
    sampler: d.sampler as GenerationSpec["sampler"],
    scheduler: d.scheduler as GenerationSpec["scheduler"],
    width: d.width,
    height: d.height,
    variants: d.variants,
    batch: items,
  };
}

export function GenerationStudio() {
  const projectId = useUi((u) => u.projectId);
  if (!projectId) return <NeedsProject module="generate" />;
  return <Studio key={projectId} projectId={projectId} />;
}

function Studio({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const project = useProject(projectId);
  const assets = useAssets(projectId);
  const styles = useStyles(projectId);
  const characters = useCharacters(projectId);
  const poses = usePoses(projectId);
  const references = useReferences(projectId);
  const models = useModels(projectId);
  const queue = useQueueGeneration();
  const [draft, setDraft] = useState<Draft>(START);
  const [jobIds, setJobIds] = useState<string[]>([]);
  const [shownAsset, setShownAsset] = useState<string | null>(null);
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) =>
    setDraft((d) => ({ ...d, [key]: value }));

  const categories = project.data?.config.categories ?? [];
  const category = draft.category || categories[0]?.slug || "";
  const checkpoints = (models.data ?? []).filter(
    (m) => m.kind === "checkpoint" && m.status === "installed",
  );
  const checkpointId = draft.checkpointId || checkpoints[0]?.id || "";
  const spec = useMemo(
    () => toSpec({ ...draft, checkpointId }, projectId, category),
    [draft, checkpointId, projectId, category],
  );
  const settled = useDebounced(spec);
  const check = useGenerationCheck(settled);
  // The answer shown belongs to the request as it is now, not one typed a moment ago.
  const current = settled === spec && !check.isFetching ? check.data : undefined;
  const pose = (poses.data ?? []).find((p) => p.id === draft.poseId);
  const existing = (assets.data ?? []).find((a) => a.id === draft.assetId);
  const versionsOf =
    draft.mode === "single" && draft.target === "existing" && draft.assetId
      ? draft.assetId
      : shownAsset;
  const shownName = (assets.data ?? []).find((a) => a.id === versionsOf)?.name;

  // Disabled controls say why (DD-008).
  const blocked = !checkpoints.length
    ? t("generation.noCheckpoint")
    : !spec
      ? t("generation.incomplete")
      : current && !current.ready
        ? t("generation.notReady")
        : null;
  const track = (ids: string[]) => setJobIds((cur) => [...ids, ...cur]);

  return (
    <div className={s.studio}>
      <form
        className={`panel ${s.column}`}
        aria-label={t("generation.settings")}
        onSubmit={(e) => {
          e.preventDefault();
          if (!spec || !current?.ready) return;
          queue.mutate(spec, {
            onSuccess: (q) => {
              setJobIds(q.jobs.map((j) => j.id));
              setShownAsset(q.asset_ids[0] ?? null);
              // Queueing again makes new versions of this asset, not a second asset.
              if (draft.mode === "single" && q.asset_ids[0]) {
                setDraft((d) => ({ ...d, target: "existing", assetId: q.asset_ids[0] ?? "" }));
              }
            },
          });
        }}
      >
        <div className={s.tabs} role="group" aria-label={t("generation.mode")}>
          {(["single", "batch"] as const).map((m) => (
            <button
              key={m}
              type="button"
              className="btn ghost"
              aria-pressed={draft.mode === m}
              onClick={() => set("mode", m)}
            >
              {t(`generation.modes.${m}`)}
            </button>
          ))}
        </div>

        {draft.mode === "single" ? (
          <fieldset className={s.fieldset}>
            <legend className="label">{t("generation.asset")}</legend>
            <div className={s.row}>
              {(["new", "existing"] as const).map((target) => (
                <label key={target} className={s.radio}>
                  <input
                    type="radio"
                    name="target"
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
                  aria-label={t("generation.asset")}
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
                <CategorySelect
                  categories={categories}
                  value={category}
                  onChange={(v) => set("category", v)}
                />
                <label className={s.field}>
                  <span className="label">{t("generation.name")}</span>
                  <input
                    className="input"
                    maxLength={200}
                    value={draft.name}
                    onChange={(e) => set("name", e.target.value)}
                  />
                </label>
              </div>
            )}
          </fieldset>
        ) : (
          <>
            <div className={s.field}>
              <label className="label" htmlFor="gen-items">
                {t("generation.items")}
              </label>
              <textarea
                id="gen-items"
                className="input"
                rows={5}
                value={draft.items}
                placeholder={t("generation.itemsHint")}
                aria-describedby="gen-items-hint"
                onChange={(e) => set("items", e.target.value)}
              />
              <span id="gen-items-hint" className="muted" style={{ fontSize: 12 }}>
                {t("generation.itemsCount", { count: batchItems(draft.items).length })}
              </span>
            </div>
            <CategorySelect
              categories={categories}
              value={category}
              onChange={(v) => set("category", v)}
            />
          </>
        )}
        {!categories.length && project.data && (
          <p className="muted" style={{ margin: 0 }}>
            {t("generation.noCategories")}
          </p>
        )}

        <div className={s.pair}>
          <Choice
            label={t("generation.style")}
            value={draft.styleId}
            onChange={(v) => set("styleId", v)}
            options={(styles.data ?? []).filter((x) => !x.archived_at)}
          />
          <Choice
            label={t("generation.character")}
            value={draft.characterId}
            onChange={(v) => set("characterId", v)}
            options={(characters.data ?? []).filter((x) => !x.archived_at)}
          />
        </div>

        <div className={s.field}>
          <Choice
            label={t("generation.pose")}
            value={draft.poseId}
            onChange={(v) => set("poseId", v)}
            options={(poses.data ?? []).filter((x) => !x.archived_at)}
          />
          <div className={s.poseBox}>
            {pose ? (
              <PoseThumb points={pose.keypoints} aspect={pose.aspect} />
            ) : (
              <span className="muted" style={{ fontSize: 12 }}>
                {t("generation.noPose")}
              </span>
            )}
            {pose && (
              <Num
                label={t("generation.poseStrength")}
                value={draft.poseStrength}
                onChange={(v) => set("poseStrength", v)}
                min={0}
                max={2}
                step={0.05}
              />
            )}
            <Link to="/poses" className="btn ghost" style={{ marginLeft: "auto" }}>
              {t("generation.editPoses")}
            </Link>
          </div>
        </div>

        <div className={s.pair}>
          <Choice
            label={t("generation.reference")}
            value={draft.referenceId}
            onChange={(v) => set("referenceId", v)}
            options={references.data ?? []}
          />
          {draft.referenceId && (
            <Num
              label={t("generation.referenceWeight")}
              value={draft.referenceWeight}
              onChange={(v) => set("referenceWeight", v)}
              min={0}
              max={2}
              step={0.05}
            />
          )}
        </div>
        {draft.referenceId && !draft.poseId && (
          <p className="muted" style={{ margin: 0, fontSize: 12 }}>
            {t("generation.referenceCopiesPose")}
          </p>
        )}
        <div className={s.pair}>
          <Choice
            label={t("generation.init")}
            value={draft.initId}
            onChange={(v) => set("initId", v)}
            options={references.data ?? []}
          />
          {draft.initId && (
            <Num
              label={t("generation.denoise")}
              value={draft.denoise}
              onChange={(v) => set("denoise", v)}
              min={0.05}
              max={1}
              step={0.05}
            />
          )}
        </div>

        <div className={s.field}>
          <label className="label" htmlFor="gen-prompt">
            {t("generation.prompt")}
          </label>
          <textarea
            id="gen-prompt"
            className="input"
            rows={3}
            maxLength={2000}
            value={draft.prompt}
            aria-describedby="gen-prompt-hint"
            onChange={(e) => set("prompt", e.target.value)}
          />
          <span id="gen-prompt-hint" className="muted" style={{ fontSize: 12 }}>
            {t("generation.promptHint")}
          </span>
        </div>
        <label className={s.field}>
          <span className="label">{t("generation.negative")}</span>
          <textarea
            className="input"
            rows={2}
            maxLength={2000}
            value={draft.negative}
            onChange={(e) => set("negative", e.target.value)}
          />
        </label>

        <div className={s.field}>
          <span className="label" id="variants-label">
            {t("generation.variants")}
          </span>
          <div className={s.row} role="group" aria-labelledby="variants-label">
            {VARIANT_COUNTS.map((n) => (
              <button
                key={n}
                type="button"
                className="btn"
                aria-pressed={draft.variants === n}
                onClick={() => set("variants", n)}
              >
                {n}
              </button>
            ))}
          </div>
        </div>

        <details className={s.details}>
          <summary className="label">{t("generation.parameters")}</summary>
          <div className={s.pair}>
            <label className={s.field}>
              <span className="label">{t("generation.checkpoint")}</span>
              <select
                className="input"
                value={checkpointId}
                onChange={(e) => set("checkpointId", e.target.value)}
              >
                {!checkpoints.length && <option value="">{t("generation.noCheckpoint")}</option>}
                {checkpoints.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
              </select>
            </label>
            <label className={s.field}>
              <span className="label">{t("generation.seed")}</span>
              <input
                className="input mono"
                inputMode="numeric"
                value={draft.seed}
                placeholder={t("generation.seedRandom")}
                onChange={(e) => set("seed", e.target.value.replace(/\D/g, ""))}
              />
            </label>
            <Num
              label={t("generation.steps")}
              value={draft.steps}
              onChange={(v) => set("steps", v)}
              min={1}
              max={150}
              step={1}
            />
            <Num
              label={t("generation.cfg")}
              value={draft.cfg}
              onChange={(v) => set("cfg", v)}
              min={1}
              max={30}
              step={0.5}
            />
            <Pick
              label={t("generation.sampler")}
              value={draft.sampler}
              onChange={(v) => set("sampler", v)}
              values={SAMPLERS}
            />
            <Pick
              label={t("generation.scheduler")}
              value={draft.scheduler}
              onChange={(v) => set("scheduler", v)}
              values={SCHEDULERS}
            />
            <Num
              label={t("generation.width")}
              value={draft.width}
              onChange={(v) => set("width", v)}
              min={256}
              max={2048}
              step={8}
            />
            <Num
              label={t("generation.height")}
              value={draft.height}
              onChange={(v) => set("height", v)}
              min={256}
              max={2048}
              step={8}
            />
          </div>
        </details>

        <div className={s.submit}>
          {current && (
            <span className="mono muted" style={{ fontSize: 12 }}>
              {t("generation.jobs", { count: current.jobs })}
            </span>
          )}
          <button
            type="submit"
            className="btn primary"
            disabled={!current?.ready || queue.isPending}
          >
            {t("generation.queue", { count: current?.jobs ?? 0 })}
          </button>
          {blocked && (
            <span className="muted" style={{ fontSize: 12 }}>
              {blocked}
            </span>
          )}
          <ProblemText error={queue.error} />
          {queue.isSuccess && (
            <p role="status" className="muted" style={{ margin: 0 }}>
              {t("generation.queued", { count: queue.data.jobs.length })}
            </p>
          )}
        </div>
      </form>

      <div className={s.stack}>
        <Checks check={current} error={check.error} loading={!!spec && !current} />
        <RunningJobs ids={jobIds} />
        {versionsOf && <Versions assetId={versionsOf} name={shownName} onQueued={track} />}
      </div>
    </div>
  );
}

function CategorySelect({
  categories,
  value,
  onChange,
}: {
  categories: { slug: string; name: string }[];
  value: string;
  onChange: (v: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <label className={s.field}>
      <span className="label">{t("generation.category")}</span>
      <select className="input" value={value} onChange={(e) => onChange(e.target.value)}>
        {categories.map((c) => (
          <option key={c.slug} value={c.slug}>
            {c.name}
          </option>
        ))}
      </select>
    </label>
  );
}

function Choice({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: readonly { id: string; name: string }[];
}) {
  const { t } = useTranslation();
  return (
    <label className={s.field}>
      <span className="label">{label}</span>
      <select className="input" value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{t("generation.none")}</option>
        {options.map((o) => (
          <option key={o.id} value={o.id}>
            {o.name}
          </option>
        ))}
      </select>
    </label>
  );
}

function Pick({
  label,
  value,
  onChange,
  values,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  values: readonly string[];
}) {
  return (
    <label className={s.field}>
      <span className="label">{label}</span>
      <select className="input mono" value={value} onChange={(e) => onChange(e.target.value)}>
        {values.map((x) => (
          <option key={x}>{x}</option>
        ))}
      </select>
    </label>
  );
}

function Num(props: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min: number;
  max: number;
  step: number;
}) {
  return (
    <label className={s.field}>
      <span className="label">{props.label}</span>
      <input
        className="input mono"
        type="number"
        min={props.min}
        max={props.max}
        step={props.step}
        value={props.value}
        onChange={(e) => {
          const v = e.target.valueAsNumber;
          if (!Number.isNaN(v)) props.onChange(v);
        }}
      />
    </label>
  );
}

function Checks({
  check,
  error,
  loading,
}: {
  check: Check | undefined;
  error: unknown;
  loading: boolean;
}) {
  const { t } = useTranslation();
  return (
    <section className={`panel ${s.column}`} aria-labelledby="checks">
      <h2 id="checks" className="h-panel">
        {t("generation.checks")}
      </h2>
      <ProblemText error={error} />
      {!check && !error && (
        <p className="muted" style={{ margin: 0 }}>
          {loading ? t("generation.checking") : t("generation.checksEmpty")}
        </p>
      )}
      {check && (
        <>
          <ul className={s.checks}>
            {check.problems.map((p, i) => (
              <li key={i}>
                <span className="badge s-failed">
                  <i />
                  {t("generation.problem")}
                </span>{" "}
                {t(`generation.problems.${p.code}`, { defaultValue: p.detail })}
                {p.model_id && <span className="mono muted"> · {p.model_id}</span>}
              </li>
            ))}
            {check.licence_confirmation_required.map((id) => (
              <li key={id}>
                <span className="badge s-review">
                  <i />
                  {t("generation.licence")}
                </span>{" "}
                {t("generation.licencePending", { model: id })}{" "}
                <Link to="/models">{t("generation.openModels")}</Link>
              </li>
            ))}
            {check.ready && (
              <li>
                <span className="badge s-approved">
                  <i />
                  OK
                </span>{" "}
                {t("generation.ready")}
              </li>
            )}
            {!check.engine.available && (
              <li>
                <span className="badge s-archived">
                  <i />
                  {t("engine.label")}
                </span>{" "}
                {t("generation.engineDown")}
              </li>
            )}
          </ul>
          <dl className={s.facts}>
            <dt>{t("generation.workflow")}</dt>
            <dd className="mono">
              {check.workflow.id} v{check.workflow.version}
            </dd>
            {Object.entries(check.models).map(([role, id]) => (
              <Fact key={role} term={t(`models.kinds.${role}`, { defaultValue: role })}>
                <span className="mono">{id}</span>
              </Fact>
            ))}
            <dt>{t("generation.finalPrompt")}</dt>
            <dd>{check.prompts[0] || "—"}</dd>
            {check.prompts.length > 1 && (
              <Fact term="">
                <span className="muted">
                  {t("generation.morePrompts", { count: check.prompts.length - 1 })}
                </span>
              </Fact>
            )}
            <dt>{t("generation.negative")}</dt>
            <dd>{check.negative || "—"}</dd>
          </dl>
        </>
      )}
    </section>
  );
}

function Fact({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <>
      <dt>{term}</dt>
      <dd>{children}</dd>
    </>
  );
}

/** A wait reason code (RULE-013) in the UI language; unknown reasons are shown as given. */
export function waitReason(t: TFunction, reason: string | null | undefined): string {
  const code = reason || "ENGINE_UNAVAILABLE";
  return /^[A-Z_]+$/.test(code) ? t(`waitReasons.${code}`, { defaultValue: code }) : code;
}

/** Step progress, the reason a job waits, or its error. */
export function JobProgress({ job }: { job: JobRow }) {
  const { t } = useTranslation();
  const step = stepProgress(job);
  if (job.state === "running" && step) {
    return (
      <div className={s.progress}>
        <div
          className={s.bar}
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={step.of}
          aria-valuenow={step.step}
          aria-label={t("generation.step", step)}
        >
          <i style={{ width: `${Math.round((step.step / step.of) * 100)}%` }} />
        </div>
        <span className="mono muted" style={{ fontSize: 12 }}>
          {t("generation.step", step)}
        </span>
      </div>
    );
  }
  if (job.state === "running") {
    return <span className="muted">{t("queuePage.starting")}</span>;
  }
  if (job.state === "queued") {
    return (
      <span className="muted">
        {job.wait_reason
          ? t("queuePage.waiting", { reason: waitReason(t, job.wait_reason) })
          : t("queuePage.inLine")}
      </span>
    );
  }
  if (job.error) {
    const code = String(job.error.code ?? "");
    const detail = String(job.error.detail ?? job.error.message ?? "");
    return (
      <span className={s.error} style={{ fontSize: 13 }}>
        {t(`problems.${code}`, { defaultValue: detail || t("inputs.failed") })}
      </span>
    );
  }
  return null;
}

function RunningJobs({ ids }: { ids: string[] }) {
  const { t } = useTranslation();
  const jobs = useJobSet(ids);
  const action = useJobAction();
  if (!ids.length) return null;
  return (
    <section className={`panel ${s.column}`} aria-labelledby="running">
      <div className={s.header}>
        <h2 id="running" className="h-panel">
          {t("generation.running")}
        </h2>
        <Link to="/queue" className="btn ghost">
          {t("generation.openQueue")}
        </Link>
      </div>
      <ul className={s.jobs}>
        {(jobs.data ?? []).map((job) => {
          const seed = (job.params as { plan?: { seed?: number } }).plan?.seed;
          return (
            <li key={job.id} className={s.jobRow}>
              <span className={`badge ${JOB_CLASS[job.state] ?? ""}`}>
                <i />
                {t(`jobStates.${job.state}`)}
              </span>
              {seed != null && (
                <span className="mono" style={{ fontSize: 12 }}>
                  seed {seed}
                </span>
              )}
              <div className={s.grow}>
                <JobProgress job={job} />
              </div>
              {ACTIVE.includes(job.state) && (
                <button
                  type="button"
                  className="btn ghost"
                  disabled={action.isPending || job.cancel_requested}
                  onClick={() => action.mutate({ jobId: job.id, action: "cancel" })}
                >
                  {t("queuePage.cancel")}
                </button>
              )}
            </li>
          );
        })}
      </ul>
      <ProblemText error={action.error ?? jobs.error} />
    </section>
  );
}

function Versions({
  assetId,
  name,
  onQueued,
}: {
  assetId: string;
  name: string | undefined;
  onQueued: (ids: string[]) => void;
}) {
  const { t } = useTranslation();
  const versions = useVersions(assetId);
  const regenerate = useRegenerate();
  const process = useProcessVersion();
  const rows = (versions.data ?? [])
    .filter((v) => !v.deleted_at)
    .sort((a, b) => b.number - a.number);
  return (
    <section className={`panel ${s.column}`} aria-labelledby="versions">
      <h2 id="versions" className="h-panel">
        {t("generation.versionsOf", { name: name ?? "" })}
      </h2>
      {versions.isPending && (
        <p role="status" className="muted" style={{ margin: 0 }}>
          {t("inputs.loading")}
        </p>
      )}
      {versions.data && !rows.length && (
        <p className="muted" style={{ margin: 0 }}>
          {t("generation.noVersions")}
        </p>
      )}
      <div className={s.tiles}>
        {rows.map((v) => (
          <VersionTile
            key={v.id}
            version={v}
            busy={regenerate.isPending || process.isPending}
            onRetry={() => process.mutate(v.id)}
            onRegenerate={() =>
              regenerate.mutate(
                { versionId: v.id, changes: { seed: randomSeed() } },
                { onSuccess: (q) => onQueued(q.jobs.map((j) => j.id)) },
              )
            }
          />
        ))}
      </div>
      <ProblemText error={regenerate.error ?? process.error ?? versions.error} />
    </section>
  );
}

/** The version's thumbnail (made by processing, WP-09); before that, the original file. */
export function VersionImage({
  id,
  className,
  alt,
}: {
  id: string;
  className: string | undefined;
  alt: string;
}) {
  const [size, setSize] = useState<"thumb" | "original">("thumb");
  return (
    <img
      className={className}
      src={versionFileUrl(id, size)}
      alt={alt}
      loading="lazy"
      onError={() => setSize("original")}
    />
  );
}

function VersionTile({
  version,
  busy,
  onRegenerate,
  onRetry,
}: {
  version: VersionRow;
  busy: boolean;
  onRegenerate: () => void;
  onRetry: () => void;
}) {
  const { t } = useTranslation();
  const seed = (version.generation_metadata as { seed?: number }).seed;
  const error = version.processing?.error;
  return (
    <figure className={s.tile} style={{ margin: 0, cursor: "default" }}>
      <VersionImage
        id={version.id}
        className={s.thumb}
        alt={t("generation.versionAlt", { n: version.number })}
      />
      <figcaption className={s.row} style={{ justifyContent: "space-between" }}>
        <span className="mono">v{version.number}</span>
        <span className={`badge ${VERSION_CLASS[version.state] ?? ""}`}>
          <i />
          {t(`versionStates.${version.state}`)}
        </span>
      </figcaption>
      {seed != null && (
        <span className="mono muted" style={{ fontSize: 12 }}>
          seed {seed}
        </span>
      )}
      {version.state === "processing_failed" && (
        <>
          <span role="status" className={s.error} style={{ fontSize: 12 }}>
            {t("generation.processingFailed")}
            {error && `: ${t(`problems.${error.code}`, { defaultValue: error.message })}`}
          </span>
          <button type="button" className="btn" disabled={busy} onClick={onRetry}>
            {t("generation.retryProcessing")}
          </button>
        </>
      )}
      {version.generation_job_id && (
        <button type="button" className="btn ghost" disabled={busy} onClick={onRegenerate}>
          {t("generation.regenerate")}
        </button>
      )}
    </figure>
  );
}
