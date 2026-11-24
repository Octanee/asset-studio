/** Projects: every project with type, intended use, counts and pending reviews; Claude's
 * drafts waiting for the user; new, import, open, export, archive (WP-16 part 2:
 * FR-001-FR-008). */
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router";

import {
  exportConfig,
  useDrafts,
  useImportProject,
  useProjectAction,
  useProjectCounts,
  useProjectList,
} from "../api/projects";
import { useUi } from "../app/store";
import { ProblemText } from "./common";
import s from "./workspace.module.css";

export function Projects() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const setProjectId = useUi((u) => u.setProjectId);
  const currentId = useUi((u) => u.projectId);
  const [archived, setArchived] = useState(false);
  const projects = useProjectList(archived);
  const counts = useProjectCounts();
  const drafts = useDrafts();
  const action = useProjectAction();
  const importer = useImportProject();
  const [importError, setImportError] = useState(false);
  const time = new Intl.DateTimeFormat(i18n.language, { dateStyle: "short", timeStyle: "short" });

  const open = (id: string) => {
    setProjectId(id);
    void navigate("/");
  };
  const onImport = async (file: File | undefined) => {
    if (!file) return;
    setImportError(false);
    try {
      const document = JSON.parse(await file.text()) as Record<string, unknown>;
      importer.mutate(document, { onSuccess: (p) => void navigate(`/projects/${p.id}`) });
    } catch {
      setImportError(true);
    }
  };

  return (
    <div className={s.column} style={{ gap: "var(--space-4)" }}>
      {!!drafts.data?.length && (
        <section className={`panel ${s.column}`} aria-labelledby="drafts">
          <h2 id="drafts" className="h-panel" style={{ margin: 0 }}>
            {t("projects.drafts")}
          </h2>
          <p className="muted" style={{ margin: 0 }}>
            {t("projects.draftsHint")}
          </p>
          <ul style={{ margin: 0, paddingLeft: "var(--space-4)" }}>
            {drafts.data.map((d) => (
              <li key={d.id}>
                <Link to={`/projects/new?draft=${d.id}`}>
                  {String((d.config as { name?: unknown }).name ?? t("projects.unnamed"))}
                </Link>{" "}
                <span className="muted">
                  · {t(`asset.actors.${d.created_by_actor}`, { defaultValue: d.created_by_actor })}{" "}
                  · {time.format(new Date(d.created_at))}
                  {d.problems.length
                    ? ` · ${t("projects.schemaProblems", { count: d.problems.length })}`
                    : ""}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className={`panel ${s.column}`} aria-label={t("nav.projects")}>
        <div className={s.header}>
          <label className={s.radio}>
            <input
              type="checkbox"
              checked={archived}
              onChange={(e) => setArchived(e.target.checked)}
            />
            {t("projects.showArchived")}
          </label>
          <div className={s.actions}>
            <label className="btn">
              {t("projects.import")}
              <input
                type="file"
                accept="application/json,.json"
                className="visually-hidden"
                onChange={(e) => void onImport(e.target.files?.[0])}
              />
            </label>
            <Link className="btn primary" to="/projects/new">
              {t("projects.new")}
            </Link>
          </div>
        </div>
        {importError && <p className={s.error}>{t("projects.importInvalid")}</p>}
        <ProblemText error={importer.error ?? action.error ?? projects.error} />

        {projects.isPending ? (
          <p role="status" className="muted">
            {t("inputs.loading")}
          </p>
        ) : !projects.data?.length ? (
          <p className="muted" style={{ margin: 0 }}>
            {t("projects.empty")}
          </p>
        ) : (
          <div className={s.tableWrap}>
            <table className={s.table}>
              <thead>
                <tr>
                  <th scope="col">{t("projects.name")}</th>
                  <th scope="col">{t("projects.type")}</th>
                  <th scope="col">{t("projects.intendedUse")}</th>
                  <th scope="col">{t("projects.assets")}</th>
                  <th scope="col">{t("projects.awaitingReview")}</th>
                  <th scope="col">{t("projects.mcp")}</th>
                  <th scope="col">
                    <span className="visually-hidden">{t("models.actions")}</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {projects.data.map((p) => {
                  const c = counts.data?.get(p.id);
                  return (
                    <tr key={p.id} aria-current={p.id === currentId ? "true" : undefined}>
                      <td>
                        <Link to={`/projects/${p.id}`}>{p.name}</Link>
                        {p.archived_at && (
                          <span className="muted"> · {t("projects.archived")}</span>
                        )}
                      </td>
                      <td>{p.type}</td>
                      <td>
                        {t(`projects.use.${p.intended_use}`, { defaultValue: p.intended_use })}
                      </td>
                      <td className="mono">
                        {c?.assets ?? 0} / {c?.versions ?? 0}
                      </td>
                      <td className="mono">{c?.awaiting_review ?? 0}</td>
                      <td>{p.mcp_can_decide ? t("projects.mcpOn") : t("projects.mcpOff")}</td>
                      <td>
                        <span className={s.row}>
                          <button
                            type="button"
                            className="btn"
                            disabled={!!p.archived_at}
                            onClick={() => open(p.id)}
                          >
                            {t("projects.open")}
                          </button>
                          <button
                            type="button"
                            className="btn ghost"
                            onClick={() => void exportConfig(p)}
                          >
                            {t("projects.export")}
                          </button>
                          <button
                            type="button"
                            className="btn ghost"
                            disabled={action.isPending}
                            onClick={() =>
                              action.mutate({
                                kind: p.archived_at ? "restore" : "archive",
                                id: p.id,
                              })
                            }
                          >
                            {p.archived_at ? t("projects.restore") : t("projects.archive")}
                          </button>
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        <p className="muted" style={{ margin: 0 }}>
          {t("projects.countsHint")}
        </p>
      </section>
    </div>
  );
}
