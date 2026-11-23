import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { useHealth } from "../api/queries";
import type { Module } from "../app/modules";
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

export function SystemStatus() {
  const { t } = useTranslation();
  const health = useHealth();
  const state = health.isPending ? "checking" : health.isError ? "down" : "ok";
  return (
    <EmptyState title={t("nav.system")}>
      <p role="status" style={{ margin: 0 }}>
        {t("status.api")}: {t(`status.${state}`)}
        {health.data && <span className="mono"> · v{health.data.version}</span>}
      </p>
      <p style={{ margin: "var(--space-2) 0 0" }}>{t("placeholder.body", { wp: "WP-16" })}</p>
    </EmptyState>
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
