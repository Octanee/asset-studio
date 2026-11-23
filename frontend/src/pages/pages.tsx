import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { ApiError } from "../api/client";
import { useEngine, useEngineControl, useHealth } from "../api/queries";
import type { Module } from "../app/modules";
import { engineLabel } from "../app/Shell";
import { useUi, type Language, type Theme } from "../app/store";

function EmptyState({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="panel" style={{ padding: "var(--space-8)", maxWidth: 720 }}>
      <h2 className="h-title">{title}</h2>
      <div className="muted" style={{ marginTop: "var(--space-2)" }}>
        {children}
      </div>
    </section>
  );
}

/** A module whose screen is built by a later work package. */
export function Placeholder({ module }: { module: { id: Module["id"] | "projects"; wp: string } }) {
  const { t } = useTranslation();
  const name = t(`nav.${module.id}`);
  return (
    <EmptyState title={t("placeholder.title", { module: name })}>
      <p style={{ margin: 0 }}>{t("placeholder.body", { wp: module.wp })}</p>
    </EmptyState>
  );
}

function EnginePanel() {
  const { t } = useTranslation();
  const engine = useEngine();
  const control = useEngineControl();
  const e = engine.data;
  const agent = (e?.agent ?? {}) as { configured?: boolean; reachable?: boolean; reason?: string };
  // Disabled controls say why (DD-008).
  const blocked = !agent.configured
    ? t("engine.agentNotConfigured")
    : agent.reachable === false
      ? t("engine.agentDown")
      : null;
  const label = engineLabel(t, engine);
  // Known problem codes are translated; anything else shows the API's own message.
  const error =
    control.error instanceof ApiError
      ? t(`problems.${control.error.code}`, { defaultValue: control.error.message })
      : null;

  return (
    <section className="panel" style={{ padding: "var(--space-6)", maxWidth: 720 }}>
      <h2 className="h-panel">{t("engine.label")}</h2>
      <p role="status" style={{ margin: "var(--space-2) 0 0" }}>
        <span className="mono">{label.text}</span>
        {e?.version && <span className="mono muted"> · v{e.version}</span>}
      </p>
      {e && !e.available && (
        <p className="muted" style={{ margin: "var(--space-2) 0 0" }}>
          {t("engine.heldJobs")}
        </p>
      )}
      <div style={{ display: "flex", gap: "var(--space-2)", marginTop: "var(--space-4)" }}>
        {e?.available ? (
          <>
            <button
              type="button"
              className="btn"
              disabled={!!blocked || control.isPending}
              onClick={() => control.mutate("restart")}
            >
              {t("engine.restart")}
            </button>
            <button
              type="button"
              className="btn danger"
              disabled={!!blocked || control.isPending}
              onClick={() => control.mutate("stop")}
            >
              {t("engine.stop")}
            </button>
          </>
        ) : (
          <button
            type="button"
            className="btn primary"
            disabled={!!blocked || control.isPending || !e}
            onClick={() => control.mutate("start")}
          >
            {t("engine.start")}
          </button>
        )}
      </div>
      {blocked && (
        <p className="muted" style={{ margin: "var(--space-2) 0 0" }}>
          {blocked}
        </p>
      )}
      {error && (
        <p role="alert" style={{ margin: "var(--space-2) 0 0", color: "var(--st-rejected)" }}>
          {error}
        </p>
      )}
    </section>
  );
}

export function SystemStatus() {
  const { t } = useTranslation();
  const health = useHealth();
  const state = health.isPending ? "checking" : health.isError ? "down" : "ok";
  return (
    <>
      <EnginePanel />
      <EmptyState title={t("status.api")}>
        <p role="status" style={{ margin: 0 }}>
          {t("status.api")}: {t(`status.${state}`)}
          {health.data && <span className="mono"> · v{health.data.version}</span>}
        </p>
        <p style={{ margin: "var(--space-2) 0 0" }}>{t("placeholder.body", { wp: "WP-16" })}</p>
      </EmptyState>
    </>
  );
}

export function Settings() {
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
      <p className="muted" style={{ margin: "var(--space-6) 0 0" }}>
        {t("settings.rest")}
      </p>
    </section>
  );
}

export function NotFound() {
  const { t } = useTranslation();
  return (
    <EmptyState title={t("notFound.title")}>
      <Link to="/" className="btn" style={{ marginTop: "var(--space-4)" }}>
        {t("notFound.back")}
      </Link>
    </EmptyState>
  );
}
