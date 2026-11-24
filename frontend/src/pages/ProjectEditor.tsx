/** New project and project settings: a configuration editor with a live schema check,
 * Claude's drafts that only the user confirms, configuration versions with diff and
 * restore, MCP permission, clone, export and archive (WP-16 part 2: FR-001-FR-008,
 * RULE-005, RULE-010). */
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";

import { ApiError } from "../api/client";
import { useProject } from "../api/generation";
import {
  EMPTY_CONFIG,
  exportConfig,
  problemLines,
  useConfigCheck,
  useConfigVersions,
  useConfirmDraft,
  useCreateProject,
  useDiscardDraft,
  useDraft,
  useProjectAction,
  useUpdateConfig,
  type ConfigVersion,
  type ProjectConfig,
} from "../api/projects";
import { metadataDiff } from "../api/review";
import { useUi } from "../app/store";
import { ProblemText } from "./common";
import x from "./system.module.css";
import s from "./workspace.module.css";

type Config = Record<string, unknown>;
type Category = { slug: string; name: string };

function str(config: Config, key: string): string {
  const v = config[key];
  return typeof v === "string" ? v : "";
}

export function slugify(name: string): string {
  return name
    .replace(/[łŁ]/g, "l")
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 63);
}

/** The configuration form. Fields not shown here are kept and editable as JSON. */
export function ConfigEditor({
  config,
  onChange,
}: {
  config: Config;
  onChange: (c: Config) => void;
}) {
  const { t } = useTranslation();
  const check = useConfigCheck(config);
  const [json, setJson] = useState(() => JSON.stringify(config, null, 2));
  const [jsonError, setJsonError] = useState(false);
  useEffect(() => setJson(JSON.stringify(config, null, 2)), [config]);
  const set = (key: string, value: unknown) => onChange({ ...config, [key]: value });
  const categories = (Array.isArray(config.categories) ? config.categories : []) as Category[];
  const languages = Array.isArray(config.languages) ? (config.languages as string[]) : [];
  const lines = problemLines(check.data?.problems);

  return (
    <div className={s.column}>
      <div className={s.form}>
        <label className={s.field}>
          <span className="label">{t("projects.name")}</span>
          <input
            className="input"
            value={str(config, "name")}
            onChange={(e) => set("name", e.target.value)}
          />
        </label>
        <label className={s.field}>
          <span className="label">{t("projects.type")}</span>
          <input
            className="input"
            value={str(config, "type")}
            onChange={(e) => set("type", e.target.value)}
          />
        </label>
        <label className={s.field}>
          <span className="label">{t("projects.description")}</span>
          <textarea
            className="input"
            rows={3}
            value={str(config, "description")}
            onChange={(e) => set("description", e.target.value)}
          />
        </label>
        <label className={s.field}>
          <span className="label">{t("projects.languages")}</span>
          <input
            className="input"
            value={languages.join(", ")}
            onChange={(e) =>
              set(
                "languages",
                e.target.value
                  .split(",")
                  .map((l) => l.trim())
                  .filter(Boolean),
              )
            }
          />
        </label>
        <fieldset className={s.fieldset}>
          <legend className="label">{t("projects.intendedUse")}</legend>
          {(["commercial", "non_commercial"] as const).map((use) => (
            <label key={use} className={s.radio}>
              <input
                type="radio"
                name="intended_use"
                checked={config.intended_use === use}
                onChange={() => set("intended_use", use)}
              />
              {t(`projects.use.${use}`)}
            </label>
          ))}
        </fieldset>
        <label className={s.field}>
          <span className="label">{t("projects.naming")}</span>
          <input
            className="input mono"
            value={str(config, "naming")}
            onChange={(e) => set("naming", e.target.value)}
          />
        </label>
      </div>

      <fieldset className={s.fieldset}>
        <legend className="label">{t("projects.categories")}</legend>
        {categories.map((c, i) => (
          <div key={i} className={s.row}>
            <input
              className="input"
              aria-label={t("projects.categoryName", { n: i + 1 })}
              value={c.name}
              onChange={(e) => {
                const next = [...categories];
                const auto = !c.slug || c.slug === slugify(c.name);
                next[i] = { name: e.target.value, slug: auto ? slugify(e.target.value) : c.slug };
                set("categories", next);
              }}
            />
            <input
              className="input mono"
              aria-label={t("projects.categorySlug", { n: i + 1 })}
              value={c.slug}
              onChange={(e) => {
                const next = [...categories];
                next[i] = { ...c, slug: e.target.value };
                set("categories", next);
              }}
            />
            <button
              type="button"
              className="btn ghost"
              onClick={() =>
                set(
                  "categories",
                  categories.filter((_, j) => j !== i),
                )
              }
            >
              {t("projects.remove")}
            </button>
          </div>
        ))}
        <button
          type="button"
          className="btn"
          onClick={() => set("categories", [...categories, { slug: "", name: "" }])}
        >
          {t("projects.addCategory")}
        </button>
      </fieldset>

      <details>
        <summary>{t("projects.advanced")}</summary>
        <p className="muted">{t("projects.advancedHint")}</p>
        <textarea
          className="input mono"
          aria-label={t("projects.advanced")}
          rows={14}
          value={json}
          onChange={(e) => setJson(e.target.value)}
          onBlur={() => {
            try {
              const parsed = JSON.parse(json) as unknown;
              if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
                setJsonError(false);
                onChange(parsed as Config);
                return;
              }
            } catch {
              // not JSON: shown below
            }
            setJsonError(true);
          }}
          style={{ width: "100%" }}
        />
        {jsonError && <p className={s.error}>{t("projects.jsonInvalid")}</p>}
      </details>

      <section aria-live="polite">
        {check.data?.valid ? (
          <p className={x.ok} style={{ margin: 0 }}>
            {t("projects.schemaOk")}
          </p>
        ) : lines.length ? (
          <>
            <p className={x.bad} style={{ margin: 0 }}>
              {t("projects.schemaProblems", { count: lines.length })}
            </p>
            <ul className="mono" style={{ margin: "var(--space-2) 0 0" }}>
              {lines.map((l) => (
                <li key={l}>{l}</li>
              ))}
            </ul>
          </>
        ) : null}
      </section>
    </div>
  );
}

function useValid(config: Config): boolean {
  return useConfigCheck(config).data?.valid === true;
}

function Items({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <div>
      <h3 className="label">{title}</h3>
      <ul style={{ margin: 0 }}>
        {items.map((a) => (
          <li key={a}>{a}</li>
        ))}
      </ul>
    </div>
  );
}

// --- new project ------------------------------------------------------------------------------

export function NewProject() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const draft = useDraft(params.get("draft"));
  const setProjectId = useUi((u) => u.setProjectId);
  const [config, setConfig] = useState<Config>({ ...EMPTY_CONFIG });
  const create = useCreateProject();
  const confirm = useConfirmDraft();
  const discard = useDiscardDraft();
  const valid = useValid(config);
  useEffect(() => {
    if (draft.data) setConfig(draft.data.config);
  }, [draft.data]);
  const d = draft.data;
  const pending = !d || d.status === "pending";

  const done = (id: string) => {
    setProjectId(id);
    void navigate(`/projects/${id}`);
  };
  const submit = () => {
    const body = config as unknown as ProjectConfig;
    if (d) confirm.mutate({ id: d.id, config: body }, { onSuccess: (p) => done(p.id) });
    else create.mutate(body, { onSuccess: (p) => done(p.id) });
  };

  return (
    <div className={s.column} style={{ gap: "var(--space-4)", maxWidth: 960 }}>
      <section className={`panel ${s.column}`}>
        <div className={s.header}>
          <h2 className="h-panel" style={{ margin: 0 }}>
            {d ? t("projects.draftTitle") : t("projects.newTitle")}
          </h2>
          <Link className="btn ghost" to="/projects">
            {t("projects.back")}
          </Link>
        </div>
        {d ? (
          <>
            <p className="muted" style={{ margin: 0 }}>
              {t("projects.draftBy", {
                actor: t(`asset.actors.${d.created_by_actor}`, {
                  defaultValue: d.created_by_actor,
                }),
              })}
            </p>
            {d.description && <blockquote style={{ margin: 0 }}>{d.description}</blockquote>}
            <Items title={t("projects.assumptions")} items={d.assumptions} />
            <Items title={t("projects.missing")} items={d.missing} />
            <p className="muted" style={{ margin: 0 }}>
              {t("projects.reviseHint")} <span className="mono">{d.id}</span>
            </p>
            {!pending && (
              <p role="alert" style={{ margin: 0 }}>
                {t("projects.draftHandled", {
                  status: t(`projects.draftStatus.${d.status}`, { defaultValue: d.status }),
                })}
              </p>
            )}
          </>
        ) : (
          <p className="muted" style={{ margin: 0 }}>
            {t("projects.newHint")}
          </p>
        )}
      </section>

      <section className={`panel ${s.column}`}>
        <ConfigEditor config={config} onChange={setConfig} />
        <ProblemText error={create.error ?? confirm.error ?? discard.error ?? draft.error} />
        <div className={s.row}>
          <button
            type="button"
            className="btn primary"
            disabled={!valid || !pending || create.isPending || confirm.isPending}
            title={!valid ? t("projects.fixFirst") : undefined}
            onClick={submit}
          >
            {t("projects.create")}
          </button>
          {d && pending && (
            <button
              type="button"
              className="btn ghost"
              disabled={discard.isPending}
              onClick={() => discard.mutate(d.id, { onSuccess: () => void navigate("/projects") })}
            >
              {t("projects.discardDraft")}
            </button>
          )}
        </div>
      </section>
    </div>
  );
}

// --- project settings ------------------------------------------------------------------------

function VersionDiff({
  version,
  current,
  currentNumber,
  onClose,
}: {
  version: ConfigVersion;
  current: Config;
  currentNumber: number;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const rows = metadataDiff(version.config, current).filter((r) => !r.same);
  return (
    <div className={s.column}>
      <div className={s.header}>
        <h3 className="label" style={{ margin: 0 }}>
          {t("projects.diffTitle", { a: version.version, b: currentNumber })}
        </h3>
        <button type="button" className="btn ghost" onClick={onClose}>
          {t("projects.close")}
        </button>
      </div>
      {rows.length ? (
        <table className={s.table}>
          <tbody>
            {rows.map((r) => (
              <tr key={r.key}>
                <th scope="row" className="mono">
                  {r.key}
                </th>
                <td className={`mono ${x.bad}`}>{r.a}</td>
                <td className={`mono ${x.ok}`}>{r.b}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="muted" style={{ margin: 0 }}>
          {t("projects.noDiff")}
        </p>
      )}
    </div>
  );
}

export function ProjectSettings() {
  const { t, i18n } = useTranslation();
  const { projectId = "" } = useParams();
  const navigate = useNavigate();
  const setProjectId = useUi((u) => u.setProjectId);
  const project = useProject(projectId);
  const versions = useConfigVersions(projectId);
  const update = useUpdateConfig(projectId);
  const action = useProjectAction();
  const [config, setConfig] = useState<Config | null>(null);
  const [note, setNote] = useState("");
  const [breaking, setBreaking] = useState<string[] | null>(null);
  const [compare, setCompare] = useState<ConfigVersion | null>(null);
  const [cloneName, setCloneName] = useState<string | null>(null);
  const p = project.data;
  useEffect(() => {
    if (p) setConfig(p.config as unknown as Config);
  }, [p]);
  const valid = useValid(config ?? {});
  const time = new Intl.DateTimeFormat(i18n.language, { dateStyle: "short", timeStyle: "short" });
  if (!p || !config) {
    return (
      <>
        <ProblemText error={project.error} />
        {project.isPending && (
          <p role="status" className="muted">
            {t("inputs.loading")}
          </p>
        )}
      </>
    );
  }
  const current = p.config as unknown as Config;
  const changed = JSON.stringify(current) !== JSON.stringify(config);

  const save = (acknowledge: boolean) =>
    update.mutate(
      { config: config as unknown as ProjectConfig, acknowledge_breaking: acknowledge, note },
      {
        onSuccess: () => {
          setBreaking(null);
          setNote("");
        },
        onError: (e) => {
          if (e instanceof ApiError && e.code === "CONFIG_BREAKING_CHANGE") {
            setBreaking((e.problem.changes as string[] | undefined) ?? []);
          }
        },
      },
    );
  const breakingError =
    update.error instanceof ApiError && update.error.code === "CONFIG_BREAKING_CHANGE";

  return (
    <div className={s.column} style={{ gap: "var(--space-4)", maxWidth: 960 }}>
      <section className={`panel ${s.column}`}>
        <div className={s.header}>
          <h2 className="h-panel" style={{ margin: 0 }}>
            {p.name}{" "}
            <span className="mono muted">
              {t("projects.configVersion", { n: p.current_config_version })}
            </span>
            {p.archived_at && <span className="muted"> · {t("projects.archived")}</span>}
          </h2>
          <div className={s.actions}>
            <button
              type="button"
              className="btn"
              disabled={!!p.archived_at}
              onClick={() => {
                setProjectId(p.id);
                void navigate("/");
              }}
            >
              {t("projects.open")}
            </button>
            <button type="button" className="btn" onClick={() => void exportConfig(p)}>
              {t("projects.export")}
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => setCloneName(t("projects.cloneDefault", { name: p.name }))}
            >
              {t("projects.clone")}
            </button>
            <button
              type="button"
              className="btn"
              disabled={action.isPending}
              onClick={() =>
                action.mutate({ kind: p.archived_at ? "restore" : "archive", id: p.id })
              }
            >
              {p.archived_at ? t("projects.restore") : t("projects.archive")}
            </button>
          </div>
        </div>
        {cloneName !== null && (
          <div className={s.row}>
            <label className={s.field}>
              <span className="label">{t("projects.cloneName")}</span>
              <input
                className="input"
                value={cloneName}
                onChange={(e) => setCloneName(e.target.value)}
              />
            </label>
            <button
              type="button"
              className="btn primary"
              disabled={!cloneName.trim() || action.isPending}
              onClick={() =>
                action.mutate(
                  { kind: "clone", id: p.id, name: cloneName.trim() },
                  {
                    onSuccess: (c) => {
                      setCloneName(null);
                      void navigate(`/projects/${(c as { id: string }).id}`);
                    },
                  },
                )
              }
            >
              {t("projects.cloneConfirm")}
            </button>
            <button type="button" className="btn ghost" onClick={() => setCloneName(null)}>
              {t("settings.cancel")}
            </button>
          </div>
        )}
        <ProblemText error={action.error} />
      </section>

      <section className={`panel ${s.column}`} aria-labelledby="mcp-permission">
        <h2 id="mcp-permission" className="h-panel" style={{ margin: 0 }}>
          {t("projects.mcpTitle")}
        </h2>
        <label className={s.radio}>
          <input
            type="checkbox"
            checked={p.mcp_can_decide}
            disabled={action.isPending}
            onChange={(e) => action.mutate({ kind: "mcp", id: p.id, allow: e.target.checked })}
          />
          {t("projects.mcpAllow")}
        </label>
        <p className="muted" style={{ margin: 0 }}>
          {t("projects.mcpHint")}
        </p>
      </section>

      <section className={`panel ${s.column}`} aria-labelledby="configuration">
        <h2 id="configuration" className="h-panel" style={{ margin: 0 }}>
          {t("projects.configuration")}
        </h2>
        <ConfigEditor config={config} onChange={setConfig} />
        <label className={s.field}>
          <span className="label">{t("projects.note")}</span>
          <input
            className="input"
            value={note}
            maxLength={500}
            onChange={(e) => setNote(e.target.value)}
          />
        </label>
        {breaking && (
          <div role="alert" className={s.column}>
            <p className={x.warn} style={{ margin: 0 }}>
              {t("projects.breaking")}
            </p>
            <ul style={{ margin: 0 }}>
              {breaking.map((b) => (
                <li key={b}>{b}</li>
              ))}
            </ul>
          </div>
        )}
        <ProblemText error={breakingError ? null : update.error} />
        <div className={s.row}>
          <button
            type="button"
            className="btn primary"
            disabled={!changed || !valid || update.isPending}
            title={!changed ? t("projects.noChanges") : !valid ? t("projects.fixFirst") : undefined}
            onClick={() => save(breaking !== null)}
          >
            {breaking ? t("projects.saveAnyway") : t("projects.saveVersion")}
          </button>
          <button
            type="button"
            className="btn ghost"
            disabled={!changed}
            onClick={() => {
              setConfig(current);
              setBreaking(null);
            }}
          >
            {t("projects.discardChanges")}
          </button>
        </div>
      </section>

      <section className={`panel ${s.column}`} aria-labelledby="versions">
        <h2 id="versions" className="h-panel" style={{ margin: 0 }}>
          {t("projects.versions")}
        </h2>
        <div className={s.tableWrap}>
          <table className={s.table}>
            <thead>
              <tr>
                <th scope="col">{t("projects.version")}</th>
                <th scope="col">{t("settings.auditTime")}</th>
                <th scope="col">{t("settings.auditActor")}</th>
                <th scope="col">{t("projects.note")}</th>
                <th scope="col">
                  <span className="visually-hidden">{t("models.actions")}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {(versions.data ?? []).map((v) => (
                <tr key={v.version}>
                  <td className="mono">v{v.version}</td>
                  <td className="mono">{time.format(new Date(v.created_at))}</td>
                  <td>
                    {t(`asset.actors.${v.created_by_actor}`, {
                      defaultValue: v.created_by_actor,
                    })}
                  </td>
                  <td>{v.note}</td>
                  <td>
                    {v.version !== p.current_config_version && (
                      <span className={s.row}>
                        <button type="button" className="btn ghost" onClick={() => setCompare(v)}>
                          {t("projects.diff")}
                        </button>
                        <button
                          type="button"
                          className="btn"
                          onClick={() => {
                            setConfig(v.config);
                            setNote(t("projects.restoredNote", { n: v.version }));
                            setBreaking(null);
                          }}
                        >
                          {t("projects.restoreVersion")}
                        </button>
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {compare && (
          <VersionDiff
            version={compare}
            current={current}
            currentNumber={p.current_config_version}
            onClose={() => setCompare(null)}
          />
        )}
        <p className="muted" style={{ margin: 0 }}>
          {t("projects.restoreHint")}
        </p>
      </section>
    </div>
  );
}
