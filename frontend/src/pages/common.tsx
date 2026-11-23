/** Shared parts of the project-input screens (WP-07). */
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";

import { ApiError } from "../api/client";
import s from "./workspace.module.css";

/** Shown when no project is chosen in the top bar. */
export function NeedsProject({ module }: { module: string }) {
  const { t } = useTranslation();
  return (
    <section className="panel" style={{ padding: "var(--space-8)", maxWidth: 720 }}>
      <h2 className="h-title">{t(`nav.${module}`)}</h2>
      <p className="muted" style={{ margin: "var(--space-2) 0 0" }}>
        {t("inputs.needsProject")}
      </p>
    </section>
  );
}

/** A known problem code is translated; anything else shows the API's own message. */
export function problemText(t: TFunction, error: unknown): string {
  if (error instanceof ApiError) {
    return t(`problems.${error.code}`, { defaultValue: error.message });
  }
  return t("inputs.failed");
}

export function ProblemText({ error }: { error: unknown }) {
  const { t } = useTranslation();
  if (!error) return null;
  return (
    <p role="alert" className={s.error}>
      {problemText(t, error)}
    </p>
  );
}

export function linesOf(text: string): string[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}
