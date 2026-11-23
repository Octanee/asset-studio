/** Queue: every job with its state, progress, reason for waiting and errors; cancel and
 * retry (WP-08: FR-038, FR-040-FR-043, RULE-012, RULE-013). */
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import {
  ACTIVE,
  generationInfo,
  useAssets,
  useJobAction,
  useJobs,
  type JobRow,
  type JobState,
} from "../api/generation";
import { useEngine } from "../api/queries";
import { useUi } from "../app/store";
import { ProblemText } from "./common";
import { JOB_CLASS, JobProgress, VersionImage, waitReason } from "./GenerationStudio";
import s from "./workspace.module.css";

const FILTERS = ["running", "queued", "failed", "interrupted", "completed", "cancelled"] as const;
const RETRYABLE: readonly string[] = ["failed", "interrupted"];

export function duration(job: JobRow): string | null {
  if (!job.started_at || !job.finished_at) return null;
  const ms = Date.parse(job.finished_at) - Date.parse(job.started_at);
  const sec = Math.max(0, Math.round(ms / 1000));
  return sec >= 60 ? `${Math.floor(sec / 60)} min ${sec % 60} s` : `${sec} s`;
}

export function Queue() {
  const { t } = useTranslation();
  const projectId = useUi((u) => u.projectId);
  const [onlyProject, setOnlyProject] = useState(false);
  const [filter, setFilter] = useState<JobState | "all">("all");
  const jobs = useJobs({ projectId: onlyProject ? projectId : null });
  const assets = useAssets(projectId);
  const action = useJobAction();
  const rows = jobs.data ?? [];
  const count = (state: string) => rows.filter((j) => j.state === state).length;
  const shown = rows.filter((j) => filter === "all" || j.state === filter);
  const retryable = rows.filter((j) => RETRYABLE.includes(j.state));
  const names = new Map((assets.data ?? []).map((a) => [a.id, a.name]));

  return (
    <section className={`panel ${s.column}`} aria-label={t("nav.queue")}>
      <div className={s.header}>
        <div className={s.row} role="group" aria-label={t("queuePage.filter")}>
          <button
            type="button"
            className="btn ghost"
            aria-pressed={filter === "all"}
            onClick={() => setFilter("all")}
          >
            {t("queuePage.all", { count: rows.length })}
          </button>
          {FILTERS.map((f) => (
            <button
              key={f}
              type="button"
              className="btn ghost"
              aria-pressed={filter === f}
              onClick={() => setFilter(f)}
            >
              {t(`jobStates.${f}`)} {count(f)}
            </button>
          ))}
        </div>
        <div className={s.actions}>
          {projectId && (
            <label className={s.radio}>
              <input
                type="checkbox"
                checked={onlyProject}
                onChange={(e) => setOnlyProject(e.target.checked)}
              />
              {t("queuePage.onlyProject")}
            </label>
          )}
          <button
            type="button"
            className="btn"
            disabled={!retryable.length || action.isPending}
            onClick={() => {
              for (const job of retryable) action.mutate({ jobId: job.id, action: "retry" });
            }}
          >
            {t("queuePage.retryAll", { count: retryable.length })}
          </button>
        </div>
      </div>

      <GpuPanel />
      <ProblemText error={action.error ?? jobs.error} />

      {jobs.isPending ? (
        <p role="status" className="muted">
          {t("inputs.loading")}
        </p>
      ) : !shown.length ? (
        <p className="muted" style={{ margin: 0 }}>
          {rows.length ? t("queuePage.noneInFilter") : t("queuePage.empty")}
        </p>
      ) : (
        <div className={s.tableWrap}>
          <table className={s.table}>
            <thead>
              <tr>
                <th scope="col">
                  <span className="visually-hidden">{t("queuePage.preview")}</span>
                </th>
                <th scope="col">{t("queuePage.job")}</th>
                <th scope="col">{t("queuePage.details")}</th>
                <th scope="col" style={{ width: 240 }}>
                  {t("queuePage.progress")}
                </th>
                <th scope="col">{t("queuePage.state")}</th>
                <th scope="col">
                  <span className="visually-hidden">{t("models.actions")}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {shown.map((job) => (
                <JobLine
                  key={job.id}
                  job={job}
                  names={names}
                  busy={action.isPending}
                  onAction={(a) => action.mutate({ jobId: job.id, action: a })}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function JobLine({
  job,
  names,
  busy,
  onAction,
}: {
  job: JobRow;
  names: Map<string, string>;
  busy: boolean;
  onAction: (action: "cancel" | "retry") => void;
}) {
  const { t } = useTranslation();
  const info = generationInfo(job);
  const versions = (job.result as { versions?: string[] }).versions ?? [];
  const kind = t(`jobKinds.${job.kind}`, { defaultValue: job.kind });
  const title =
    job.kind === "generate"
      ? (info.assetId && names.get(info.assetId)) || t("queuePage.otherAsset")
      : kind;
  const took = duration(job);
  return (
    <tr>
      <td>
        {versions[0] ? (
          <VersionImage id={versions[0]} className={s.jobThumb} alt="" />
        ) : (
          <span className={s.jobThumb} aria-hidden="true" />
        )}
      </td>
      <td>
        <b>{title}</b>
        <div className="muted" style={{ fontSize: 12 }}>
          {kind} · {new Date(job.created_at).toLocaleString()}
          {job.attempts > 1 && ` · ${t("queuePage.attempt", { n: job.attempts })}`}
        </div>
      </td>
      <td className="mono muted" style={{ fontSize: 12 }}>
        {[info.workflow, info.seed != null ? `seed ${info.seed}` : null]
          .filter(Boolean)
          .join(" · ") || job.lane}
      </td>
      <td>
        {job.state === "completed" ? (
          <span className="mono muted" style={{ fontSize: 12 }}>
            {took ?? "—"}
          </span>
        ) : (
          <JobProgress job={job} />
        )}
      </td>
      <td>
        <span className={`badge ${JOB_CLASS[job.state] ?? ""}`}>
          <i />
          {t(`jobStates.${job.state}`)}
        </span>
      </td>
      <td>
        {ACTIVE.includes(job.state) && (
          <button
            type="button"
            className="btn ghost"
            disabled={busy || job.cancel_requested}
            onClick={() => onAction("cancel")}
          >
            {job.cancel_requested ? t("queuePage.cancelling") : t("queuePage.cancel")}
          </button>
        )}
        {RETRYABLE.includes(job.state) && (
          <button type="button" className="btn" disabled={busy} onClick={() => onAction("retry")}>
            {job.state === "interrupted" ? t("queuePage.resume") : t("queuePage.retry")}
          </button>
        )}
        {job.state === "completed" && job.kind === "generate" && (
          <Link to="/generate" className="btn ghost">
            {t("queuePage.openStudio")}
          </Link>
        )}
      </td>
    </tr>
  );
}

/** The GPU, what runs on it and why GPU jobs wait (RULE-012, RULE-013). */
function GpuPanel() {
  const { t } = useTranslation();
  const engine = useEngine();
  const e = engine.data;
  const device = e?.devices[0];
  const total = device?.vram_total_mb ?? null;
  const used = total != null && device?.vram_free_mb != null ? total - device.vram_free_mb : null;
  return (
    <div className={`panel ${s.gpu}`}>
      <span className="label">GPU</span>
      {device ? (
        <span className="mono">
          {device.name}
          {used != null &&
            total != null &&
            ` · ${(used / 1024).toFixed(1)} / ${(total / 1024).toFixed(1)} GB`}
        </span>
      ) : (
        <span className="muted">—</span>
      )}
      {used != null && total ? (
        <div className={`${s.bar} ${s.grow}`} aria-hidden="true">
          <i style={{ width: `${Math.round((used / total) * 100)}%` }} />
        </div>
      ) : (
        <span className={s.grow} />
      )}
      <span className="muted" style={{ fontSize: 13 }}>
        {e && !e.available
          ? t("queuePage.held", { reason: waitReason(t, e.reason) })
          : t("queuePage.oneAtATime")}
      </span>
    </div>
  );
}
