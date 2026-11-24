/** Settings: appearance and queue, data locations with backup and restore, the MCP
 * connection and the audit log (WP-16: FR-110-FR-112, FR-115, FR-125, UXQ-02). */
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { NavLink } from "react-router";

import { useJobSet } from "../api/generation";
import { useProjects } from "../api/queries";
import {
  ACTORS,
  formatBytes,
  useAppSettings,
  useAuditActions,
  useAuditLog,
  useBackups,
  useCreateBackup,
  useRestoreBackup,
  useSystemStatus,
  useUpdateSettings,
  type Backup,
} from "../api/system";
import { useUi, type Language, type Theme } from "../app/store";
import { ProblemText } from "./common";
import { JOB_CLASS } from "./GenerationStudio";
import x from "./system.module.css";
import s from "./workspace.module.css";

export type SettingsSection = "general" | "data" | "mcp" | "audit";
const SECTIONS: { id: SettingsSection; path: string }[] = [
  { id: "general", path: "/settings" },
  { id: "data", path: "/settings/data" },
  { id: "mcp", path: "/settings/mcp" },
  { id: "audit", path: "/settings/audit" },
];

export function Settings({ section }: { section: SettingsSection }) {
  const { t } = useTranslation();
  return (
    <div className={s.column}>
      <nav className={x.tabs} aria-label={t("settings.sections")}>
        {SECTIONS.map((sec) => (
          <NavLink key={sec.id} to={sec.path} end className={x.tab}>
            {t(`settings.section.${sec.id}`)}
          </NavLink>
        ))}
      </nav>
      {section === "general" && <General />}
      {section === "data" && (
        <>
          <Locations />
          <Backups />
        </>
      )}
      {section === "mcp" && <McpConnection />}
      {section === "audit" && <AuditLog />}
    </div>
  );
}

// --- general --------------------------------------------------------------------------------

function General() {
  const { t } = useTranslation();
  const { theme, language, setTheme, setLanguage } = useUi();
  const choice = <T extends string>(
    name: string,
    value: T,
    current: T,
    set: (v: T) => void,
    label: string,
  ) => (
    <label style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", minHeight: 32 }}>
      <input type="radio" name={name} checked={current === value} onChange={() => set(value)} />
      {label}
    </label>
  );

  return (
    <>
      <section className="panel" style={{ padding: "var(--space-6)", maxWidth: 720 }}>
        <h2 className="h-panel">{t("settings.appearance")}</h2>
        <div
          style={{
            display: "flex",
            gap: "var(--space-8)",
            flexWrap: "wrap",
            marginTop: "var(--space-4)",
          }}
        >
          <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
            <legend className="label">{t("settings.theme")}</legend>
            {choice<Theme>("theme", "dark", theme, setTheme, t("settings.themeDark"))}
            {choice<Theme>("theme", "light", theme, setTheme, t("settings.themeLight"))}
          </fieldset>
          <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
            <legend className="label">{t("settings.language")}</legend>
            {choice<Language>("language", "pl", language, setLanguage, t("settings.languagePl"))}
            {choice<Language>("language", "en", language, setLanguage, t("settings.languageEn"))}
          </fieldset>
        </div>
      </section>
      <QueuePause />
    </>
  );
}

/** Pause the whole queue: running jobs finish, nothing new starts except backup and restore. */
export function QueuePause() {
  const { t } = useTranslation();
  const settings = useAppSettings();
  const update = useUpdateSettings();
  const paused = settings.data?.queue_paused ?? false;
  return (
    <section className="panel" style={{ padding: "var(--space-6)", maxWidth: 720 }}>
      <h2 className="h-panel">{t("settings.queue")}</h2>
      <p role="status" style={{ margin: "var(--space-2) 0" }}>
        {paused ? t("settings.queuePaused") : t("settings.queueRunning")}
      </p>
      <p className="muted" style={{ margin: "0 0 var(--space-4)" }}>
        {t("settings.queueHint")}
      </p>
      <button
        type="button"
        className={paused ? "btn primary" : "btn"}
        disabled={!settings.data || update.isPending}
        onClick={() => update.mutate({ queue_paused: !paused })}
      >
        {paused ? t("settings.resumeQueue") : t("settings.pauseQueue")}
      </button>
      <ProblemText error={update.error} />
    </section>
  );
}

// --- data locations and backups ------------------------------------------------------------

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </>
  );
}

function Locations() {
  const { t, i18n } = useTranslation();
  const status = useSystemStatus();
  const st = status.data;
  const yesNo = (v: boolean) => (v ? t("settings.configured") : t("settings.notConfigured"));
  return (
    <section className="panel" style={{ padding: "var(--space-6)", maxWidth: 880 }}>
      <h2 className="h-panel">{t("settings.locations")}</h2>
      <ProblemText error={status.error} />
      {st && (
        <dl className={x.facts} style={{ marginTop: "var(--space-4)" }}>
          <Fact label={t("settings.library")}>
            <span className="mono">{st.storage.volume as string}</span> ·{" "}
            {t("settings.libraryUsage", {
              files: st.storage.files as number,
              size: formatBytes(st.storage.bytes as number, i18n.language),
            })}
          </Fact>
          <Fact label={t("settings.free")}>
            {formatBytes(st.storage.free_bytes as number | null, i18n.language)} /{" "}
            {formatBytes(st.storage.total_bytes as number | null, i18n.language)}
          </Fact>
          <Fact label={t("settings.backupsFolder")}>{yesNo(st.backups.configured as boolean)}</Fact>
          <Fact label={t("settings.exportRoots")}>
            {t("settings.exportRootsCount", { count: st.locations.export_roots as number })}
          </Fact>
          <Fact label={t("settings.modelsFolder")}>
            {yesNo(st.locations.models_folder as boolean)}
          </Fact>
          <Fact label={t("settings.engine")}>
            <span className="mono">{st.locations.engine_url as string}</span>
          </Fact>
        </dl>
      )}
      <p className="muted" style={{ margin: "var(--space-4) 0 0" }}>
        {t("settings.locationsHint")}
      </p>
    </section>
  );
}

function FollowJob({ id, onDone }: { id: string; onDone: () => void }) {
  const { t } = useTranslation();
  const jobs = useJobSet([id]);
  const job = jobs.data?.[0];
  const finished = job && !["queued", "running"].includes(job.state);
  useEffect(() => {
    if (finished) onDone();
  }, [finished, onDone]);
  if (!job) return null;
  const error = job.error as { code?: string; message?: string } | null;
  return (
    <p role="status" style={{ margin: "var(--space-2) 0 0" }}>
      {t(`jobKinds.${job.kind}`, { defaultValue: job.kind })}:{" "}
      <span className={`badge ${JOB_CLASS[job.state] ?? ""}`}>
        <i />
        {t(`jobStates.${job.state}`)}
      </span>
      {job.wait_reason && (
        <span className="muted">
          {" "}
          · {t(`waitReasons.${job.wait_reason}`, { defaultValue: job.wait_reason })}
        </span>
      )}
      {error?.code && (
        <span className={x.bad}>
          {" "}
          · {t(`problems.${error.code}`, { defaultValue: error.message ?? error.code })}
        </span>
      )}
    </p>
  );
}

function Backups() {
  const { t, i18n } = useTranslation();
  const client = useQueryClient();
  const backups = useBackups();
  const status = useSystemStatus();
  const create = useCreateBackup();
  const restore = useRestoreBackup();
  const [confirming, setConfirming] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const time = new Intl.DateTimeFormat(i18n.language, { dateStyle: "medium", timeStyle: "short" });
  const empty = status.data?.storage.empty === true;
  const configured = backups.data?.configured ?? false;
  const refresh = () => {
    void client.invalidateQueries({ queryKey: ["backups"] });
    void client.invalidateQueries({ queryKey: ["system"] });
    void client.invalidateQueries({ queryKey: ["projects"] });
  };
  // Disabled controls say why (DD-008).
  const restoreBlocked = !empty ? t("settings.restoreNotEmpty") : null;

  return (
    <section className="panel" style={{ padding: "var(--space-6)", maxWidth: 880 }}>
      <div className={s.header}>
        <h2 className="h-panel" style={{ margin: 0 }}>
          {t("settings.backups")}
        </h2>
        <button
          type="button"
          className="btn primary"
          disabled={!configured || create.isPending}
          onClick={() => create.mutate(undefined, { onSuccess: (job) => setJobId(job.id) })}
        >
          {t("settings.createBackup")}
        </button>
      </div>
      <p className="muted" style={{ margin: "var(--space-2) 0 0" }}>
        {configured ? t("settings.backupHint") : t("settings.backupsNotConfigured")}
      </p>
      {jobId && <FollowJob id={jobId} onDone={refresh} />}
      <ProblemText error={create.error ?? restore.error ?? backups.error} />

      {!backups.data?.items.length ? (
        <p className="muted" style={{ margin: "var(--space-4) 0 0" }}>
          {t("settings.noBackups")}
        </p>
      ) : (
        <div className={s.tableWrap} style={{ marginTop: "var(--space-4)" }}>
          <table className={s.table}>
            <thead>
              <tr>
                <th scope="col">{t("settings.backupName")}</th>
                <th scope="col">{t("settings.backupCreated")}</th>
                <th scope="col">{t("settings.backupSize")}</th>
                <th scope="col">{t("settings.backupContents")}</th>
                <th scope="col">
                  <span className="visually-hidden">{t("models.actions")}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {backups.data.items.map((b: Backup) => (
                <tr key={b.name}>
                  <td className="mono">{b.name}</td>
                  <td>{b.created_at ? time.format(new Date(b.created_at)) : "—"}</td>
                  <td className="mono">{formatBytes(b.bytes, i18n.language)}</td>
                  <td>
                    {b.readable ? (
                      t("settings.backupTotals", {
                        files: b.totals.files ?? 0,
                        rows: b.totals.rows ?? 0,
                        models: b.models,
                      })
                    ) : (
                      <span className={x.bad}>{t("settings.backupUnreadable")}</span>
                    )}
                  </td>
                  <td>
                    {confirming === b.name ? (
                      <span className={s.row}>
                        <button
                          type="button"
                          className="btn danger"
                          disabled={restore.isPending}
                          onClick={() =>
                            restore.mutate(b.name, {
                              onSuccess: (job) => {
                                setJobId(job.id);
                                setConfirming(null);
                              },
                            })
                          }
                        >
                          {t("settings.confirmRestore")}
                        </button>
                        <button
                          type="button"
                          className="btn ghost"
                          onClick={() => setConfirming(null)}
                        >
                          {t("settings.cancel")}
                        </button>
                      </span>
                    ) : (
                      <button
                        type="button"
                        className="btn"
                        disabled={!!restoreBlocked || !b.readable}
                        title={restoreBlocked ?? undefined}
                        onClick={() => setConfirming(b.name)}
                      >
                        {t("settings.restore")}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {restoreBlocked && !!backups.data?.items.length && (
        <p className="muted" style={{ margin: "var(--space-2) 0 0" }}>
          {restoreBlocked}
        </p>
      )}
    </section>
  );
}

// --- MCP ------------------------------------------------------------------------------------

function McpConnection() {
  const { t } = useTranslation();
  const status = useSystemStatus();
  const mcp = status.data?.mcp as { configured?: boolean; port?: number } | undefined;
  const url = `http://127.0.0.1:${mcp?.port ?? 8411}/mcp`;
  const command = `claude mcp add --transport http asset-studio ${url} --header "Authorization: Bearer <token>"`;
  return (
    <section className="panel" style={{ padding: "var(--space-6)", maxWidth: 880 }}>
      <h2 className="h-panel">{t("settings.mcp")}</h2>
      <p role="status" style={{ margin: "var(--space-2) 0" }}>
        {mcp?.configured ? (
          <span className={x.ok}>{t("settings.mcpConfigured")}</span>
        ) : (
          <span className={x.warn}>{t("settings.mcpNotConfigured")}</span>
        )}
      </p>
      <dl className={x.facts}>
        <Fact label={t("settings.mcpUrl")}>
          <span className="mono">{url}</span>
        </Fact>
      </dl>
      <p style={{ margin: "var(--space-4) 0 var(--space-2)" }}>{t("settings.mcpConnect")}</p>
      <code className={`mono ${x.code}`}>{command}</code>
      <p className="muted" style={{ margin: "var(--space-4) 0 0" }}>
        {t("settings.mcpToken")}
      </p>
      <p className="muted" style={{ margin: "var(--space-2) 0 0" }}>
        {t("settings.mcpRules")}
      </p>
    </section>
  );
}

// --- audit log (FR-115, UXQ-02) ----------------------------------------------------------------

function AuditLog() {
  const { t, i18n } = useTranslation();
  const projects = useProjects();
  const [projectId, setProjectId] = useState<string | null>(null);
  const [actor, setActor] = useState<string | null>(null);
  const [action, setAction] = useState<string | null>(null);
  const actions = useAuditActions(projectId);
  const log = useAuditLog({ projectId, actor, action });
  const rows = log.data?.pages.flat() ?? [];
  const names = new Map((projects.data ?? []).map((p) => [p.id, p.name]));
  const time = new Intl.DateTimeFormat(i18n.language, { dateStyle: "short", timeStyle: "medium" });

  return (
    <section className={`panel ${s.column}`} aria-label={t("settings.section.audit")}>
      <div className={s.row} role="group" aria-label={t("settings.auditFilters")}>
        <label className={s.field}>
          <span className="label">{t("settings.auditProject")}</span>
          <select
            className="input"
            value={projectId ?? ""}
            onChange={(e) => setProjectId(e.target.value || null)}
          >
            <option value="">{t("settings.auditAny")}</option>
            {(projects.data ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
        <label className={s.field}>
          <span className="label">{t("settings.auditActor")}</span>
          <select
            className="input"
            value={actor ?? ""}
            onChange={(e) => setActor(e.target.value || null)}
          >
            <option value="">{t("settings.auditAny")}</option>
            {ACTORS.map((a) => (
              <option key={a} value={a}>
                {t(`asset.actors.${a}`, { defaultValue: a })}
              </option>
            ))}
          </select>
        </label>
        <label className={s.field}>
          <span className="label">{t("settings.auditAction")}</span>
          <select
            className="input"
            value={action ?? ""}
            onChange={(e) => setAction(e.target.value || null)}
          >
            <option value="">{t("settings.auditAny")}</option>
            {(actions.data ?? []).map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </label>
      </div>
      <ProblemText error={log.error} />
      {log.isPending ? (
        <p role="status" className="muted">
          {t("inputs.loading")}
        </p>
      ) : !rows.length ? (
        <p className="muted" style={{ margin: 0 }}>
          {t("settings.auditEmpty")}
        </p>
      ) : (
        <div className={s.tableWrap}>
          <table className={s.table}>
            <thead>
              <tr>
                <th scope="col">{t("settings.auditTime")}</th>
                <th scope="col">{t("settings.auditActor")}</th>
                <th scope="col">{t("settings.auditAction")}</th>
                <th scope="col">{t("settings.auditProject")}</th>
                <th scope="col">{t("settings.auditDetails")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((e) => (
                <tr key={e.id}>
                  <td className="mono">{time.format(new Date(e.at))}</td>
                  <td>{t(`asset.actors.${e.actor}`, { defaultValue: e.actor })}</td>
                  <td>
                    {t(`asset.actions.${e.action.replace(/\./g, "_")}`, {
                      defaultValue: e.action,
                    })}
                    <div className="mono muted">{e.action}</div>
                  </td>
                  <td>{e.project_id ? (names.get(e.project_id) ?? "—") : "—"}</td>
                  <td className="mono muted" style={{ maxWidth: 360, overflowWrap: "anywhere" }}>
                    {Object.keys(e.data).length ? JSON.stringify(e.data) : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {log.hasNextPage && (
        <button
          type="button"
          className="btn"
          disabled={log.isFetchingNextPage}
          onClick={() => void log.fetchNextPage()}
        >
          {t("settings.auditMore")}
        </button>
      )}
    </section>
  );
}
