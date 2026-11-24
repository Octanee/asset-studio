/** Dashboard: what needs attention in the current project, versions by state, the newest
 * versions, recent failures and activity, with quick actions (WP-16: FR-100). */
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { useQueueCounts } from "../api/queries";
import { STATES } from "../api/review";
import { formatBytes, useAuditLog, useDashboard } from "../api/system";
import { useUi } from "../app/store";
import { NeedsProject, ProblemText } from "./common";
import { VERSION_CLASS, VersionImage } from "./GenerationStudio";
import x from "./system.module.css";
import s from "./workspace.module.css";

function Card({
  to,
  label,
  count,
  attention,
  hint,
}: {
  to: string;
  label: string;
  count: number | string;
  attention: boolean;
  hint?: string;
}) {
  return (
    <Link to={to} className={x.card} data-attention={attention}>
      <span className="label">{label}</span>
      <span className={x.count}>{count}</span>
      {hint && <span className="muted">{hint}</span>}
    </Link>
  );
}

export function Dashboard() {
  const { t, i18n } = useTranslation();
  const projectId = useUi((u) => u.projectId);
  const dashboard = useDashboard(projectId ?? "");
  const queue = useQueueCounts();
  const activity = useAuditLog({ projectId, actor: null, action: null });
  if (!projectId) return <NeedsProject module="dashboard" />;

  const d = dashboard.data;
  const time = new Intl.DateTimeFormat(i18n.language, { dateStyle: "short", timeStyle: "short" });
  const byState = d?.versions_by_state ?? {};
  const most = Math.max(1, ...Object.values(byState));
  const recent = (activity.data?.pages[0] ?? []).slice(0, 10);
  const backup = d?.last_backup;

  return (
    <div className={s.column} style={{ gap: "var(--space-4)" }}>
      <section className={`panel ${s.column}`} aria-labelledby="attention">
        <div className={s.header}>
          <h2 id="attention" className="h-panel" style={{ margin: 0 }}>
            {t("dashboard.attention")}
          </h2>
          <div className={s.actions}>
            <Link className="btn" to="/library">
              {t("dashboard.openLibrary")}
            </Link>
            <Link className="btn" to="/generate?mode=batch">
              {t("dashboard.batch")}
            </Link>
            <Link className="btn primary" to="/generate">
              {t("dashboard.newGeneration")}
            </Link>
          </div>
        </div>
        <ProblemText error={dashboard.error} />
        {d && (
          <div className={x.cards}>
            <Card
              to="/review"
              label={t("dashboard.awaitingReview")}
              count={d.attention.awaiting_review}
              attention={d.attention.awaiting_review > 0}
            />
            <Card
              to="/library"
              label={t("dashboard.processingFailed")}
              count={d.attention.processing_failed}
              attention={d.attention.processing_failed > 0}
            />
            <Card
              to="/queue"
              label={t("dashboard.failedJobs")}
              count={d.attention.failed_jobs}
              attention={d.attention.failed_jobs > 0}
              hint={t("dashboard.lastDays", { count: 7 })}
            />
            <Card
              to="/models"
              label={t("dashboard.licence")}
              count={d.attention.licence_warnings}
              attention={d.attention.licence_warnings > 0}
            />
            <Card
              to="/queue"
              label={t("dashboard.queue")}
              count={`${queue.data?.running ?? 0} / ${queue.data?.queued ?? 0}`}
              attention={false}
              hint={t("dashboard.runningQueued")}
            />
            <Card
              to="/settings/data"
              label={t("dashboard.backup")}
              count={backup ? formatBytes(backup.bytes, i18n.language) : "—"}
              attention={d.attention.backup_due}
              hint={
                backup?.created_at
                  ? time.format(new Date(backup.created_at))
                  : t("dashboard.noBackup")
              }
            />
          </div>
        )}
      </section>

      <div className={x.grid}>
        <section className={`panel ${s.column}`} aria-labelledby="by-state">
          <h2 id="by-state" className="h-panel" style={{ margin: 0 }}>
            {t("dashboard.byState")}
          </h2>
          <ul className={x.bars}>
            {STATES.map((state) => (
              <li key={state}>
                <span className={`badge ${VERSION_CLASS[state] ?? ""}`}>
                  <i />
                  {t(`versionStates.${state}`)}
                </span>
                <span className={x.track} aria-hidden="true">
                  <span
                    className={x.fill}
                    style={{ display: "block", width: `${((byState[state] ?? 0) / most) * 100}%` }}
                  />
                </span>
                <span className="mono">{byState[state] ?? 0}</span>
              </li>
            ))}
          </ul>
        </section>

        <section className={`panel ${s.column}`} aria-labelledby="activity">
          <h2 id="activity" className="h-panel" style={{ margin: 0 }}>
            {t("dashboard.activity")}
          </h2>
          {!recent.length ? (
            <p className="muted" style={{ margin: 0 }}>
              {t("dashboard.noActivity")}
            </p>
          ) : (
            <ul className={x.activity}>
              {recent.map((e) => (
                <li key={e.id}>
                  <span className="mono muted">{time.format(new Date(e.at))}</span>{" "}
                  {t(`asset.actions.${e.action.replace(/\./g, "_")}`, { defaultValue: e.action })}
                  <span className="muted">
                    {" "}
                    · {t(`asset.actors.${e.actor}`, { defaultValue: e.actor })}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <Link to="/settings/audit">{t("dashboard.allActivity")}</Link>
        </section>
      </div>

      <section className={`panel ${s.column}`} aria-labelledby="latest">
        <h2 id="latest" className="h-panel" style={{ margin: 0 }}>
          {t("dashboard.latest")}
        </h2>
        {d && !d.latest_versions.length ? (
          <p className="muted" style={{ margin: 0 }}>
            {t("dashboard.noVersions")}
          </p>
        ) : (
          <div className={s.tiles}>
            {(d?.latest_versions ?? []).map((v) => (
              <Link key={v.id} to={`/library/${v.asset_id}`} className={s.tile}>
                <VersionImage
                  id={v.id}
                  className={s.thumb}
                  alt={t("library.thumbAlt", { name: v.asset_name, n: v.number })}
                />
                <span className={s.name} title={v.asset_name}>
                  {v.asset_name} <span className="mono muted">v{v.number}</span>
                </span>
                <span className={`badge ${VERSION_CLASS[v.state] ?? ""}`}>
                  <i />
                  {t(`versionStates.${v.state}`)}
                </span>
              </Link>
            ))}
          </div>
        )}
      </section>

      {!!d?.failed_jobs.length && (
        <section className={`panel ${s.column}`} aria-labelledby="failed">
          <h2 id="failed" className="h-panel" style={{ margin: 0 }}>
            {t("dashboard.failures")}
          </h2>
          <ul className={x.activity}>
            {d.failed_jobs.map((j) => (
              <li key={j.id}>
                <span className="mono muted">
                  {j.finished_at ? time.format(new Date(j.finished_at)) : ""}
                </span>{" "}
                {t(`jobKinds.${j.kind}`, { defaultValue: j.kind })}
                {j.code && (
                  <span className="muted">
                    {" "}
                    · {t(`problems.${j.code}`, { defaultValue: j.message ?? j.code })}
                  </span>
                )}
              </li>
            ))}
          </ul>
          <Link to="/queue">{t("dashboard.openQueue")}</Link>
        </section>
      )}
    </div>
  );
}
