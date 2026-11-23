import * as Menu from "@radix-ui/react-dropdown-menu";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, NavLink, Outlet, useLocation } from "react-router";

import { useHealth, useLiveEvents, useProjects, useQueueCounts } from "../api/queries";
import { CommandPalette } from "./CommandPalette";
import { MODULES, moduleFor } from "./modules";
import s from "./Shell.module.css";
import { useUi } from "./store";

function Icon({ d }: { d: string }) {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={d} />
    </svg>
  );
}

function Rail() {
  const { t } = useTranslation();
  return (
    <nav className={s.rail} aria-label={t("nav.label")}>
      <div className={s.logo} aria-hidden="true">
        <span />
        <span />
        <span />
        <span />
      </div>
      {MODULES.map((m) => (
        <NavLink
          key={m.id}
          to={m.path}
          end={m.path === "/"}
          className={s.railLink}
          aria-label={t(`nav.${m.id}`)}
          title={t(`nav.${m.id}`)}
        >
          <Icon d={m.icon} />
        </NavLink>
      ))}
    </nav>
  );
}

function BottomBar() {
  const { t } = useTranslation();
  return (
    <nav className={s.bottombar} aria-label={t("nav.quick")}>
      {MODULES.filter((m) => m.phone).map((m) => (
        <NavLink key={m.id} to={m.path} end={m.path === "/"} className={s.bottomLink}>
          {t(`nav.${m.id}`)}
        </NavLink>
      ))}
    </nav>
  );
}

function ProjectSwitcher() {
  const { t } = useTranslation();
  const projects = useProjects();
  const projectId = useUi((u) => u.projectId);
  const setProjectId = useUi((u) => u.setProjectId);
  const current = projects.data?.find((p) => p.id === projectId);

  return (
    <Menu.Root>
      <Menu.Trigger className="btn ghost" aria-label={t("project.switch")}>
        <span className={s.swatch} aria-hidden="true" />
        <span style={{ fontWeight: 600 }}>{current?.name ?? t("project.none")}</span>
        <svg
          width="14"
          height="14"
          viewBox="0 0 14 14"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          aria-hidden="true"
        >
          <path d="M3 5l4 4 4-4" />
        </svg>
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Content className={s.menu} align="start" sideOffset={4}>
          {projects.isError && (
            <Menu.Item className={s.menuItem} disabled>
              {t("project.error")}
            </Menu.Item>
          )}
          {projects.data?.length === 0 && (
            <Menu.Item className={s.menuItem} disabled>
              {t("project.empty")}
            </Menu.Item>
          )}
          <Menu.RadioGroup value={current?.id ?? ""} onValueChange={(id) => setProjectId(id)}>
            {projects.data?.map((p) => (
              <Menu.RadioItem key={p.id} value={p.id} className={s.menuItem}>
                <span style={{ width: 14 }} aria-hidden="true">
                  <Menu.ItemIndicator>✓</Menu.ItemIndicator>
                </span>
                {p.name}
              </Menu.RadioItem>
            ))}
          </Menu.RadioGroup>
          <Menu.Separator className={s.menuSep} />
          <Menu.Item className={s.menuItem} asChild>
            <Link to="/projects">{t("project.all")}</Link>
          </Menu.Item>
        </Menu.Content>
      </Menu.Portal>
    </Menu.Root>
  );
}

function QueueIndicator() {
  const { t } = useTranslation();
  const queue = useQueueCounts();
  const q = queue.data;
  let badge: { cls: string; text: string };
  if (!q) badge = { cls: "s-archived", text: t("queue.unknown") };
  else if (q.running > 0)
    badge = { cls: "s-processing", text: t("queue.running", { count: q.running }) };
  else if (q.failed > 0) badge = { cls: "s-failed", text: t("queue.failed", { count: q.failed }) };
  else badge = { cls: "s-generated", text: t("queue.idle") };

  return (
    <Link to="/queue" className="btn ghost" title={t("queue.label")} data-testid="queue-indicator">
      <span className={`badge ${badge.cls}`}>
        <i />
        {badge.text}
      </span>
      {q && q.queued > 0 && <span className="muted">{t("queue.queued", { count: q.queued })}</span>}
      {q && q.workers === 0 && <span className="muted">{t("queue.noWorker")}</span>}
    </Link>
  );
}

function EngineStatus() {
  const { t } = useTranslation();
  const health = useHealth();
  // Engine health arrives with the engine adapter (WP-05); until then only the API is known.
  const down = health.isError;
  return (
    <Link to="/system" className="btn ghost" title={t("engine.label")}>
      <span
        className={s.dot}
        aria-hidden="true"
        style={{ background: down ? "var(--st-failed)" : "var(--st-archived)" }}
      />
      <span className={`mono ${s.narrowText}`}>
        {down ? t("engine.apiDown") : t("engine.notConnected")}
      </span>
    </Link>
  );
}

function LanguageSwitch() {
  const { t } = useTranslation();
  const language = useUi((u) => u.language);
  const setLanguage = useUi((u) => u.setLanguage);
  return (
    <div role="group" aria-label={t("language.label")} style={{ display: "flex", gap: 4 }}>
      {(["pl", "en"] as const).map((lng) => (
        <button
          key={lng}
          type="button"
          className="btn ghost"
          aria-pressed={language === lng}
          onClick={() => setLanguage(lng)}
          lang={lng}
        >
          {t(`language.${lng}`)}
        </button>
      ))}
    </div>
  );
}

function TopBar({ onSearch }: { onSearch: () => void }) {
  const { t } = useTranslation();
  const { pathname } = useLocation();
  const module = moduleFor(pathname);
  const extra = pathname.startsWith("/projects")
    ? "projects"
    : pathname.startsWith("/system")
      ? "system"
      : null;
  const title = module ? t(`nav.${module.id}`) : extra ? t(`nav.${extra}`) : t("app.name");

  return (
    <header className={s.topbar}>
      <ProjectSwitcher />
      <span className={`muted ${s.narrowHide}`} aria-hidden="true">
        /
      </span>
      <h1 className={s.title}>{title}</h1>
      <div className={s.searchSlot}>
        <button type="button" className={s.search} onClick={onSearch}>
          <span>{t("search.open")}…</span>
          <kbd className={s.kbd}>{t("search.hint")}</kbd>
        </button>
      </div>
      <QueueIndicator />
      <EngineStatus />
      <LanguageSwitch />
    </header>
  );
}

/** Keeps the document in step with UI preferences: language (FR-125) and theme. */
function usePreferences() {
  const { i18n } = useTranslation();
  const language = useUi((u) => u.language);
  const theme = useUi((u) => u.theme);
  useEffect(() => {
    if (i18n.language !== language) void i18n.changeLanguage(language);
    document.documentElement.lang = language;
  }, [i18n, language]);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);
}

export function AppShell() {
  const { t } = useTranslation();
  const [paletteOpen, setPaletteOpen] = useState(false);
  usePreferences();
  useLiveEvents(true);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((open) => !open);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className={s.app}>
      <a href="#content" className={`btn ${s.skip}`}>
        {t("app.skip")}
      </a>
      <Rail />
      <div className={s.main}>
        <TopBar onSearch={() => setPaletteOpen(true)} />
        <main id="content" className={s.content} tabIndex={-1}>
          <Outlet />
        </main>
      </div>
      <BottomBar />
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
    </div>
  );
}
