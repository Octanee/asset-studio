import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

type ApiState = "checking" | "ok" | "down";

/** Placeholder shell for WP-00. The real app shell (rail, top bar) arrives in WP-06. */
export function App() {
  const { t, i18n } = useTranslation();
  const [api, setApi] = useState<ApiState>("checking");

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/v1/system/health", { signal: controller.signal })
      .then((r) => setApi(r.ok ? "ok" : "down"))
      .catch((e: unknown) => {
        if (!(e instanceof DOMException && e.name === "AbortError")) setApi("down");
      });
    return () => controller.abort();
  }, []);

  return (
    <main
      style={{
        padding: "var(--space-8)",
        display: "flex",
        flexDirection: "column",
        gap: "var(--space-4)",
      }}
    >
      <h1 style={{ margin: 0, font: "700 40px/44px var(--font-display)" }}>{t("app.name")}</h1>
      <p style={{ margin: 0, color: "var(--ink-muted)" }}>{t("app.tagline")}</p>
      <p role="status">
        {t("status.api")}: {t(`status.${api}`)}
      </p>
      <div style={{ display: "flex", gap: "var(--space-2)" }}>
        <button type="button" onClick={() => void i18n.changeLanguage("pl")}>
          PL
        </button>
        <button type="button" onClick={() => void i18n.changeLanguage("en")}>
          EN
        </button>
      </div>
    </main>
  );
}
