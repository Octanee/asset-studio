/** LoRA training: datasets from approved versions and uploads with captions, the run with
 * family, base model, steps and the time estimate (SDXL warning), progress, cancel and the
 * trained LoRA (WP-13: FR-070-FR-075, RULE-016, RULE-017). */
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { useCancelJob, useModels } from "../api/models";
import { usePublishable } from "../api/publishing";
import {
  duration,
  itemFileUrl,
  useCreateDataset,
  useDatasetActions,
  useDatasets,
  useEstimate,
  useItems,
  useRuns,
  useStartRun,
  type Dataset,
  type Family,
} from "../api/training";
import { useUi } from "../app/store";
import { NeedsProject, ProblemText } from "./common";
import { JOB_CLASS, JobProgress, VersionImage } from "./GenerationStudio";
import x from "./system.module.css";
import s from "./workspace.module.css";

const MIN_IMAGES = 5;

export function Training() {
  const projectId = useUi((u) => u.projectId);
  const datasets = useDatasets(projectId ?? "");
  const [selected, setSelected] = useState<string | null>(null);
  useEffect(() => {
    const first = datasets.data?.[0]?.id ?? null;
    if (!selected || !datasets.data?.some((d) => d.id === selected)) setSelected(first);
  }, [datasets.data, selected]);
  if (!projectId) return <NeedsProject module="training" />;
  const dataset = datasets.data?.find((d) => d.id === selected) ?? null;

  return (
    <div className={s.column} style={{ gap: "var(--space-4)" }}>
      <div className={x.grid}>
        <DatasetList
          projectId={projectId}
          datasets={datasets.data ?? []}
          selected={selected}
          onSelect={setSelected}
        />
        {dataset && <RunPanel dataset={dataset} projectId={projectId} />}
      </div>
      {dataset && <DatasetPanel dataset={dataset} projectId={projectId} />}
      <Runs projectId={projectId} datasets={datasets.data ?? []} />
    </div>
  );
}

function DatasetList({
  projectId,
  datasets,
  selected,
  onSelect,
}: {
  projectId: string;
  datasets: Dataset[];
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  const { t } = useTranslation();
  const create = useCreateDataset(projectId);
  const [name, setName] = useState("");
  const [trigger, setTrigger] = useState("");
  return (
    <section className={`panel ${s.column}`} aria-labelledby="datasets">
      <h2 id="datasets" className="h-panel" style={{ margin: 0 }}>
        {t("training.datasets")}
      </h2>
      {!datasets.length && (
        <p className="muted" style={{ margin: 0 }}>
          {t("training.noDatasets")}
        </p>
      )}
      <ul className={s.list}>
        {datasets.map((d) => (
          <li key={d.id}>
            <button
              type="button"
              className={s.item}
              aria-current={d.id === selected ? "true" : undefined}
              onClick={() => onSelect(d.id)}
            >
              <span>{d.name}</span>
              <span className="mono muted">
                {d.trigger_word} · {t("training.imagesCount", { count: d.images })}
              </span>
            </button>
          </li>
        ))}
      </ul>
      <form
        className={s.column}
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate(
            { name: name.trim(), trigger_word: trigger.trim() },
            {
              onSuccess: (d) => {
                setName("");
                setTrigger("");
                onSelect(d.id);
              },
            },
          );
        }}
      >
        <h3 className="label" style={{ margin: 0 }}>
          {t("training.newDataset")}
        </h3>
        <label className={s.field}>
          <span className="label">{t("training.name")}</span>
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className={s.field}>
          <span className="label">{t("training.trigger")}</span>
          <input
            className="input mono"
            value={trigger}
            placeholder="exz_woman"
            onChange={(e) => setTrigger(e.target.value)}
          />
        </label>
        <p className="muted" style={{ margin: 0 }}>
          {t("training.triggerHint")}
        </p>
        <ProblemText error={create.error} />
        <button
          type="submit"
          className="btn"
          disabled={!name.trim() || trigger.trim().length < 2 || create.isPending}
        >
          {t("training.createDataset")}
        </button>
      </form>
    </section>
  );
}

function DatasetPanel({ dataset, projectId }: { dataset: Dataset; projectId: string }) {
  const { t } = useTranslation();
  const items = useItems(dataset.id);
  const actions = useDatasetActions(dataset.id);
  const publishable = usePublishable(projectId);
  const [picking, setPicking] = useState(false);
  const [chosen, setChosen] = useState<string[]>([]);
  const inDataset = new Set((items.data ?? []).map((i) => i.asset_version_id));
  const candidates = (publishable.data ?? []).filter((v) => !inDataset.has(v.id));
  const error =
    actions.addVersions.error ??
    actions.upload.error ??
    actions.caption.error ??
    actions.remove.error ??
    items.error;

  return (
    <section className={`panel ${s.column}`} aria-labelledby="dataset">
      <div className={s.header}>
        <h2 id="dataset" className="h-panel" style={{ margin: 0 }}>
          {dataset.name} <span className="mono muted">{dataset.trigger_word}</span>
        </h2>
        <div className={s.actions}>
          <button type="button" className="btn" onClick={() => setPicking((p) => !p)}>
            {t("training.addApproved")}
          </button>
          <label className="btn">
            {t("training.upload")}
            <input
              type="file"
              multiple
              accept="image/png,image/jpeg,image/webp"
              className="visually-hidden"
              onChange={(e) => {
                const files = Array.from(e.target.files ?? []);
                if (files.length) actions.upload.mutate(files);
                e.target.value = "";
              }}
            />
          </label>
        </div>
      </div>
      <p className="muted" style={{ margin: 0 }}>
        {t("training.datasetHint", { min: MIN_IMAGES })}
      </p>
      <ProblemText error={error} />

      {picking && (
        <div className={s.column}>
          {!candidates.length ? (
            <p className="muted" style={{ margin: 0 }}>
              {t("training.noApproved")}
            </p>
          ) : (
            <div className={`${s.tiles} ${s.small}`}>
              {candidates.map((v) => (
                <label key={v.id} className={s.tile}>
                  <input
                    type="checkbox"
                    checked={chosen.includes(v.id)}
                    onChange={(e) =>
                      setChosen((c) =>
                        e.target.checked ? [...c, v.id] : c.filter((id) => id !== v.id),
                      )
                    }
                  />
                  <VersionImage
                    id={v.id}
                    className={s.thumb}
                    alt={t("library.thumbAlt", { name: v.asset.name, n: v.number })}
                  />
                  <span className={s.name}>
                    {v.asset.name} v{v.number}
                  </span>
                </label>
              ))}
            </div>
          )}
          <div className={s.row}>
            <button
              type="button"
              className="btn primary"
              disabled={!chosen.length || actions.addVersions.isPending}
              onClick={() =>
                actions.addVersions.mutate(chosen, {
                  onSuccess: () => {
                    setChosen([]);
                    setPicking(false);
                  },
                })
              }
            >
              {t("training.addChosen", { count: chosen.length })}
            </button>
          </div>
        </div>
      )}

      {!items.data?.length ? (
        <p className="muted" style={{ margin: 0 }}>
          {t("training.empty")}
        </p>
      ) : (
        <div className={s.tiles}>
          {items.data.map((item, n) => (
            <div key={item.id} className={s.tile}>
              <img
                className={s.thumb}
                src={itemFileUrl(item.id)}
                alt={t("training.imageAlt", { n: n + 1 })}
                loading="lazy"
              />
              <span className="mono muted" style={{ fontSize: 12 }}>
                {item.source === "upload" ? t("training.uploaded") : t("training.fromLibrary")}
              </span>
              <Caption
                label={t("training.captionFor", { n: n + 1 })}
                value={item.caption}
                onSave={(text) => actions.caption.mutate({ id: item.id, text })}
              />
              <button
                type="button"
                className="btn ghost"
                onClick={() => actions.remove.mutate(item.id)}
              >
                {t("training.remove")}
              </button>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

/** FR-071: edited in place, saved when the field is left. */
function Caption({
  label,
  value,
  onSave,
}: {
  label: string;
  value: string;
  onSave: (text: string) => void;
}) {
  const [text, setText] = useState(value);
  useEffect(() => setText(value), [value]);
  return (
    <textarea
      className="input"
      aria-label={label}
      rows={2}
      value={text}
      onChange={(e) => setText(e.target.value)}
      onBlur={() => {
        if (text.trim() !== value) onSave(text.trim());
      }}
    />
  );
}

function RunPanel({ dataset, projectId }: { dataset: Dataset; projectId: string }) {
  const { t } = useTranslation();
  const models = useModels(projectId);
  const start = useStartRun();
  const [family, setFamily] = useState<Family>("sd15");
  const [baseId, setBaseId] = useState("");
  const [steps, setSteps] = useState<number | null>(null);
  const [ack, setAck] = useState(false);
  const bases = (models.data ?? []).filter(
    (m) => m.kind === "checkpoint" && m.family_id === family && m.status === "installed",
  );
  const firstBase = bases[0]?.id ?? "";
  const hasBase = bases.some((m) => m.id === baseId);
  useEffect(() => {
    if (!hasBase) setBaseId(firstBase);
  }, [hasBase, firstBase]);
  useEffect(() => {
    setSteps(null);
    setAck(false);
  }, [family, dataset.id]);
  const draft = baseId ? { dataset_id: dataset.id, family, base_model_id: baseId, steps } : null;
  const estimate = useEstimate(draft);
  const e = estimate.data;
  const blocked = !baseId
    ? t("training.noBase", { family: t(`training.family.${family}`) })
    : e?.warning && !ack && !estimate.error
      ? t("training.ackFirst")
      : null;

  return (
    <section className={`panel ${s.column}`} aria-labelledby="run">
      <h2 id="run" className="h-panel" style={{ margin: 0 }}>
        {t("training.train")}
      </h2>
      <fieldset className={s.fieldset}>
        <legend className="label">{t("training.familyLabel")}</legend>
        {(["sd15", "sdxl"] as const).map((f) => (
          <label key={f} className={s.radio}>
            <input
              type="radio"
              name="family"
              checked={family === f}
              onChange={() => setFamily(f)}
            />
            {t(`training.family.${f}`)}
          </label>
        ))}
      </fieldset>
      <label className={s.field}>
        <span className="label">{t("training.base")}</span>
        <select className="input" value={baseId} onChange={(ev) => setBaseId(ev.target.value)}>
          {bases.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name}
            </option>
          ))}
        </select>
      </label>
      <label className={s.field}>
        <span className="label">{t("training.steps")}</span>
        <input
          className="input mono"
          type="number"
          min={e?.min_steps ?? 1}
          max={e?.max_steps}
          placeholder={e ? String(e.default_steps) : ""}
          value={steps ?? ""}
          onChange={(ev) => setSteps(ev.target.value ? Number(ev.target.value) : null)}
        />
      </label>

      <ProblemText error={estimate.error} />
      {e && !estimate.error && (
        <dl className={x.facts}>
          <dt>{t("training.estimate")}</dt>
          <dd className="mono">{duration(e.seconds)}</dd>
          <dt>{t("training.stepsLabel")}</dt>
          <dd className="mono">
            {e.steps} · {e.resolution} px · {t("training.imagesCount", { count: e.images })}
          </dd>
          <dt>{t("training.gpu")}</dt>
          <dd className="mono">
            {e.vram_mb ? `${Math.round(e.vram_mb / 1024)} GB` : t("training.gpuUnknown")}
          </dd>
        </dl>
      )}
      {e?.warning && !estimate.error && (
        <div role="alert" className={s.column}>
          <p className={x.warn} style={{ margin: 0 }}>
            {t("training.sdxlWarning", {
              time: duration(e.seconds),
              recommended: Math.round(e.recommended_vram_mb / 1024),
            })}
          </p>
          <label className={s.radio}>
            <input type="checkbox" checked={ack} onChange={(ev) => setAck(ev.target.checked)} />
            {t("training.acknowledge", { time: duration(e.seconds) })}
          </label>
        </div>
      )}
      <ProblemText error={start.error} />
      <button
        type="button"
        className="btn primary"
        disabled={!draft || !e || !!estimate.error || !!blocked || start.isPending}
        title={blocked ?? undefined}
        onClick={() => draft && start.mutate({ ...draft, acknowledged_estimate: ack })}
      >
        {t("training.start")}
      </button>
      {blocked && (
        <p className="muted" style={{ margin: 0 }}>
          {blocked}
        </p>
      )}
    </section>
  );
}

function Runs({ projectId, datasets }: { projectId: string; datasets: Dataset[] }) {
  const { t, i18n } = useTranslation();
  const runs = useRuns(projectId);
  const cancel = useCancelJob();
  const names = new Map(datasets.map((d) => [d.id, d.name]));
  const time = new Intl.DateTimeFormat(i18n.language, { dateStyle: "short", timeStyle: "short" });
  if (!runs.data?.length) return null;
  return (
    <section className={`panel ${s.column}`} aria-labelledby="runs">
      <h2 id="runs" className="h-panel" style={{ margin: 0 }}>
        {t("training.runs")}
      </h2>
      <ProblemText error={cancel.error ?? runs.error} />
      <div className={s.tableWrap}>
        <table className={s.table}>
          <thead>
            <tr>
              <th scope="col">{t("training.started")}</th>
              <th scope="col">{t("training.datasetCol")}</th>
              <th scope="col">{t("training.familyLabel")}</th>
              <th scope="col">{t("queuePage.progress")}</th>
              <th scope="col">{t("training.result")}</th>
              <th scope="col">
                <span className="visually-hidden">{t("models.actions")}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {runs.data.map((r) => {
              const job = r.job;
              const active = !!job && ["queued", "running"].includes(job.state);
              return (
                <tr key={r.id}>
                  <td className="mono">{time.format(new Date(r.created_at))}</td>
                  <td>{names.get(r.dataset_id) ?? "—"}</td>
                  <td>
                    {t(`training.family.${r.family_id}`)}{" "}
                    <span className="mono muted">
                      {String(r.params.steps)} · {duration(Number(r.estimate.seconds))}
                    </span>
                  </td>
                  <td style={{ minWidth: 200 }}>
                    {job && (
                      <>
                        <span className={`badge ${JOB_CLASS[job.state] ?? ""}`}>
                          <i />
                          {t(`jobStates.${job.state}`)}
                        </span>
                        <JobProgress job={job} />
                      </>
                    )}
                  </td>
                  <td>
                    {r.output_model_id ? (
                      <Link to="/models" className="mono">
                        {r.output_model_id}
                      </Link>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td>
                    {active && job && (
                      <button
                        type="button"
                        className="btn danger"
                        disabled={cancel.isPending}
                        onClick={() => cancel.mutate(job.id)}
                      >
                        {t("training.cancel")}
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
