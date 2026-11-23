/** Review: the versions waiting for a decision, oldest first, with a large preview, technical
 * validation, duplicates, comments (incl. Claude's) and the generation metadata
 * (WP-10: FR-059-FR-064, RULE-009). */
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router";

import { useVersions } from "../api/generation";
import { fileUrl, useReviewQueue, type QueueVersion } from "../api/review";
import { useUi } from "../app/store";
import { NeedsProject, ProblemText } from "./common";
import {
  CommentsPanel,
  DuplicatesPanel,
  MetadataPanel,
  StateBadge,
  ValidationPanel,
  VersionActions,
} from "./ReviewParts";
import r from "./review.module.css";
import s from "./workspace.module.css";

export function Review() {
  const projectId = useUi((u) => u.projectId);
  if (!projectId) return <NeedsProject module="review" />;
  return <ReviewScreen key={projectId} projectId={projectId} />;
}

function typing(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName))
  );
}

function ReviewScreen({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const queue = useReviewQueue(projectId);
  const rows = queue.data ?? [];
  const wanted = params.get("version");
  const found = rows.findIndex((v) => v.id === wanted);
  const index = found >= 0 ? found : 0;
  const current = rows[index];

  const show = (v: QueueVersion | undefined) =>
    setParams(v ? { version: v.id } : {}, { replace: true });

  // ← and → move through the strip, unless the user is typing.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (typing(e.target) || e.altKey || e.ctrlKey || e.metaKey) return;
      if (e.key === "ArrowRight" && rows[index + 1]) show(rows[index + 1]);
      if (e.key === "ArrowLeft" && rows[index - 1]) show(rows[index - 1]);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (queue.isPending) {
    return (
      <p role="status" className="muted">
        {t("inputs.loading")}
      </p>
    );
  }
  if (!current) {
    return (
      <section className={`panel ${s.column}`} aria-label={t("nav.review")}>
        <ProblemText error={queue.error} />
        <h2 className="h-title">{t("review.emptyTitle")}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {t("review.empty")} <Link to="/library">{t("review.openLibrary")}</Link>
        </p>
      </section>
    );
  }

  return (
    <section className={s.stack} aria-label={t("nav.review")}>
      <div className={`panel ${s.column}`}>
        <div className={s.header}>
          <h2 className="h-panel" style={{ margin: 0 }}>
            {t("review.pending", { count: rows.length })}
          </h2>
          <span className="muted" style={{ fontSize: 12 }}>
            {t("review.keys")}
          </span>
        </div>
        <ul className={r.strip} aria-label={t("review.strip")}>
          {rows.map((v, i) => (
            <li key={v.id}>
              <button
                type="button"
                aria-current={i === index}
                aria-label={`${v.asset.name} v${v.number}`}
                onClick={() => show(v)}
              >
                <img src={fileUrl(v.id, "thumb")} alt="" loading="lazy" />
                <span className={s.name}>{v.asset.name}</span>
              </button>
            </li>
          ))}
        </ul>
      </div>
      <Current
        key={current.id}
        version={current}
        onDecided={() => show(rows[index + 1] ?? rows[index - 1])}
      />
    </section>
  );
}

function Current({ version, onDecided }: { version: QueueVersion; onDecided: () => void }) {
  const { t } = useTranslation();
  const versions = useVersions(version.asset_id);
  const previous = (versions.data ?? []).find(
    (v) => v.number < version.number && v.state !== "deleted",
  );
  return (
    <div className={r.split}>
      <figure className="panel" style={{ margin: 0, padding: "var(--space-3)" }}>
        <a href={fileUrl(version.id, version.processing?.output ? "processed" : "original")}>
          <img
            className={r.stage}
            src={fileUrl(version.id, "preview")}
            alt={t("review.previewAlt", { name: version.asset.name, n: version.number })}
            onError={(e) => {
              e.currentTarget.onerror = null;
              e.currentTarget.src = fileUrl(version.id, "original");
            }}
          />
        </a>
      </figure>
      <aside className={`panel ${s.column}`} aria-label={t("review.details")}>
        <div className={r.section}>
          <h2 className="h-title" style={{ margin: 0 }}>
            <Link to={`/library/${version.asset_id}`}>{version.asset.name}</Link>{" "}
            <span className="mono muted">v{version.number}</span>
          </h2>
          <div className={s.row}>
            <StateBadge state={version.state} />
            <span className="muted mono" style={{ fontSize: 12 }}>
              {version.asset.category}
            </span>
          </div>
        </div>
        <VersionActions version={version} compact onDone={onDecided} />
        {previous && (
          <Link
            className="btn ghost"
            to={`/review/compare?a=${previous.id}&b=${version.id}`}
            style={{ justifySelf: "start" }}
          >
            {t("review.compareWith", { n: previous.number })}
          </Link>
        )}
        <ValidationPanel versionId={version.id} />
        <DuplicatesPanel versionId={version.id} />
        <CommentsPanel versionId={version.id} />
        <MetadataPanel version={version} />
      </aside>
    </div>
  );
}
