import { useTranslation } from "react-i18next";
import { Outlet, type RouteObject } from "react-router";

import { ApiError } from "../api/client";
import { useSession } from "../api/queries";
import { AssetDetails } from "../pages/AssetDetails";
import { Compare } from "../pages/Compare";
import { GenerationStudio } from "../pages/GenerationStudio";
import { Library } from "../pages/Library";
import { Models } from "../pages/Models";
import { NotFound, Placeholder, Settings, SystemStatus } from "../pages/pages";
import { Poses } from "../pages/Poses";
import { Queue } from "../pages/Queue";
import { References } from "../pages/References";
import { Review } from "../pages/Review";
import { StyleStudio } from "../pages/StyleStudio";
import { MODULES, type ModuleId } from "./modules";

/** Modules whose screen exists; the rest show a placeholder naming their work package. */
const BUILT = new Set<ModuleId>([
  "settings",
  "styles",
  "references",
  "poses",
  "models",
  "generate",
  "queue",
  "library",
  "review",
]);
import { AppShell } from "./Shell";

/** The session cookie must exist before any other request (ADR-012). */
function SessionGate() {
  const { t } = useTranslation();
  const session = useSession();

  if (session.isPending) {
    return (
      <p role="status" className="muted" style={{ padding: "var(--space-8)" }}>
        {t("session.connecting")}
      </p>
    );
  }
  if (session.isError) {
    const notConfigured =
      session.error instanceof ApiError && session.error.code === "NOT_CONFIGURED";
    return (
      <main style={{ padding: "var(--space-8)", maxWidth: 640 }}>
        <h1 className="h-display">{t("app.name")}</h1>
        <div
          role="alert"
          className="panel"
          style={{ padding: "var(--space-6)", marginTop: "var(--space-6)" }}
        >
          <h2 className="h-title">
            {notConfigured ? t("session.notConfigured") : t("session.failed")}
          </h2>
          <p className="muted">
            {session.error instanceof ApiError ? session.error.message : t("session.hint")}
          </p>
          <button type="button" className="btn primary" onClick={() => void session.refetch()}>
            {t("session.retry")}
          </button>
        </div>
      </main>
    );
  }
  return <Outlet />;
}

export const routes: RouteObject[] = [
  {
    element: <SessionGate />,
    children: [
      {
        element: <AppShell />,
        children: [
          ...MODULES.filter((m) => !BUILT.has(m.id)).map((m) => ({
            path: m.path,
            element: <Placeholder module={m} />,
          })),
          { path: "/generate", element: <GenerationStudio /> },
          { path: "/queue", element: <Queue /> },
          { path: "/library", element: <Library /> },
          { path: "/library/:assetId", element: <AssetDetails /> },
          { path: "/review", element: <Review /> },
          { path: "/review/compare", element: <Compare /> },
          { path: "/styles", element: <StyleStudio /> },
          { path: "/references", element: <References /> },
          { path: "/poses", element: <Poses /> },
          { path: "/models", element: <Models /> },
          { path: "/settings", element: <Settings /> },
          { path: "/projects", element: <Placeholder module={{ id: "projects", wp: "WP-16" }} /> },
          { path: "/system", element: <SystemStatus /> },
          { path: "*", element: <NotFound /> },
        ],
      },
    ],
  },
];
