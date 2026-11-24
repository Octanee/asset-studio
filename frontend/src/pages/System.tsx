/** System status: each component's health, the queue, storage, library consistency and
 * backups (WP-16: NFR-003, RULE-013, Storage-and-Backup). */
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { formatBytes, useSystemStatus } from "../api/system";
import { ProblemText } from "./common";
import { waitReason } from "./GenerationStudio";
import { EnginePanel } from "./pages";
import x from "./system.module.css";
import s from "./workspace.module.css";

type Health = "ok" | "warn" | "bad";

function Row({
  name,
  health,
  children,
}: {
  name: string;
  health: Health;
  children: React.ReactNode;
}) {
  const { t } = useTranslation();
  const cls = health === "ok" ? x.ok : health === "warn" ? x.warn : x.bad;
  return (
    <tr>
      <th scope="row">{name}</th>
      <td>
        <span className={cls}>{t(`system.health.${health}`)}</span>
      </td>
      <td>{children}</td>
    </tr>
  );
}

export function SystemStatus() {
  const { t, i18n } = useTranslation();
  const status = useSystemStatus();
  const st = status.data;
  const time = new Intl.DateTimeFormat(i18n.language, { dateStyle: "medium", timeStyle: "short" });

  return (
    <div className={s.column} style={{ gap: "var(--space-4)" }}>
      <EnginePanel />
      <section className={`panel ${s.column}`} aria-labelledby="components">
        <h2 id="components" className="h-panel" style={{ margin: 0 }}>
          {t("system.components")}
        </h2>
        <ProblemText error={status.error} />
        {status.isPending && (
          <p role="status" className="muted">
            {t("inputs.loading")}
          </p>
        )}
        {st && (
          <div className={s.tableWrap}>
            <table className={s.table}>
              <thead>
                <tr>
                  <th scope="col">{t("system.component")}</th>
                  <th scope="col">{t("system.state")}</th>
                  <th scope="col">{t("system.details")}</th>
                </tr>
              </thead>
              <tbody>
                <Row name={t("status.api")} health="ok">
                  <span className="mono">v{st.api.version}</span>
                </Row>
                <Row
                  name={t("system.database")}
                  health={st.database.schema_revision === st.database.head_revision ? "ok" : "warn"}
                >
                  {t("system.schema", {
                    current: st.database.schema_revision,
                    head: st.database.head_revision,
                  })}
                </Row>
                <Row
                  name={t("system.worker")}
                  health={(st.queue.workers as unknown[]).length ? "ok" : "bad"}
                >
                  {t("system.workers", { count: (st.queue.workers as unknown[]).length })}
                </Row>
                <Row name={t("engine.label")} health={st.engine.available ? "ok" : "warn"}>
                  {st.engine.available
                    ? `${st.engine.engine}${st.engine.version ? ` v${st.engine.version}` : ""}`
                    : waitReason(t, st.engine.reason)}
                </Row>
                <Row name={t("system.queue")} health={st.queue.paused ? "warn" : "ok"}>
                  {st.queue.paused ? t("settings.queuePaused") : t("settings.queueRunning")}
                  {Object.values(st.queue.wait_reasons as Record<string, string>).map((r) => (
                    <span key={r} className="muted">
                      {" "}
                      · {waitReason(t, r)}
                    </span>
                  ))}{" "}
                  <Link to="/queue">{t("system.openQueue")}</Link>
                </Row>
                <Row name={t("settings.library")} health="ok">
                  {t("settings.libraryUsage", {
                    files: st.storage.files as number,
                    size: formatBytes(st.storage.bytes as number, i18n.language),
                  })}
                  <span className="muted">
                    {" "}
                    · {t("settings.free")}{" "}
                    {formatBytes(st.storage.free_bytes as number | null, i18n.language)}
                  </span>
                </Row>
                <Row
                  name={t("system.consistency")}
                  health={
                    (st.consistency.missing as number)
                      ? "bad"
                      : (st.consistency.orphans as number)
                        ? "warn"
                        : "ok"
                  }
                >
                  {t("system.consistencyCounts", {
                    missing: st.consistency.missing as number,
                    orphans: st.consistency.orphans as number,
                  })}
                </Row>
                <Row
                  name={t("settings.backups")}
                  health={!st.backups.configured ? "bad" : st.backups.due ? "warn" : "ok"}
                >
                  {(st.backups.last as { created_at?: string } | null)?.created_at
                    ? t("system.lastBackup", {
                        at: time.format(
                          new Date((st.backups.last as { created_at: string }).created_at),
                        ),
                      })
                    : t("dashboard.noBackup")}{" "}
                  <Link to="/settings/data">{t("system.openBackups")}</Link>
                </Row>
              </tbody>
            </table>
          </div>
        )}
        {st && (st.consistency.missing as number) > 0 && (
          <p className={x.bad} style={{ margin: 0 }}>
            {t("system.missingHint")}{" "}
            <span className="mono">{(st.consistency.missing_versions as string[]).join(", ")}</span>
          </p>
        )}
      </section>
    </div>
  );
}
