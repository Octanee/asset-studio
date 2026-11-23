/** Parts shared by Review, Asset details and Compare (WP-10): lifecycle actions, technical
 * validation, duplicates, comments and generation metadata. */
import * as Dialog from "@radix-ui/react-dialog";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import {
  fileUrl,
  useAddComment,
  useComments,
  useDeleteVersion,
  useDuplicates,
  useTransition,
  useValidation,
  type ClientAction,
  type Version,
} from "../api/review";
import { ProblemText } from "./common";
import { VERSION_CLASS } from "./GenerationStudio";
import r from "./review.module.css";
import s from "./workspace.module.css";

const ARCHIVABLE = [
  "generated",
  "awaiting_review",
  "approved",
  "rejected",
  "published",
  "processing_failed",
];

export function StateBadge({ state }: { state: string }) {
  const { t } = useTranslation();
  return (
    <span className={`badge ${VERSION_CLASS[state] ?? ""}`}>
      <i />
      {t(`versionStates.${state}`)}
    </span>
  );
}

/** The actions the user may take on a version in its state (Asset-Lifecycle). A disabled
 * action says why (DD-008). `compact` leaves out archive and delete (the review screen). */
export function VersionActions({
  version,
  onDone,
  compact = false,
}: {
  version: Version;
  onDone?: (action: ClientAction | "delete") => void;
  compact?: boolean;
}) {
  const { t } = useTranslation();
  const transition = useTransition();
  const remove = useDeleteVersion();
  const [asking, setAsking] = useState<"reject" | "withdraw" | null>(null);
  const [reason, setReason] = useState("");
  const busy = transition.isPending || remove.isPending;
  const st = version.state;
  const published = version.first_published_at != null;

  const run = (action: ClientAction, why = "") =>
    transition.mutate(
      { versionId: version.id, action, reason: why },
      {
        onSuccess: () => {
          setAsking(null);
          setReason("");
          onDone?.(action);
        },
      },
    );

  return (
    <div className={r.section}>
      <div className={s.actions}>
        {st === "awaiting_review" && (
          <>
            <button
              type="button"
              className="btn primary"
              disabled={busy}
              onClick={() => run("approve")}
            >
              {t("review.approve")}
            </button>
            <button
              type="button"
              className="btn danger"
              disabled={busy}
              aria-expanded={asking === "reject"}
              onClick={() => setAsking(asking === "reject" ? null : "reject")}
            >
              {t("review.reject")}
            </button>
          </>
        )}
        {st === "approved" && (
          <button
            type="button"
            className="btn"
            disabled={busy || published}
            title={published ? t("review.withdrawPublished") : undefined}
            aria-expanded={asking === "withdraw"}
            onClick={() => setAsking(asking === "withdraw" ? null : "withdraw")}
          >
            {t("review.withdraw")}
          </button>
        )}
        {st === "rejected" && (
          <button type="button" className="btn" disabled={busy} onClick={() => run("reopen")}>
            {t("review.reopen")}
          </button>
        )}
        {st === "processing_failed" && (
          <button
            type="button"
            className="btn"
            disabled={busy}
            onClick={() => run("retry_processing")}
          >
            {t("generation.retryProcessing")}
          </button>
        )}
        {!compact && ARCHIVABLE.includes(st) && (
          <button
            type="button"
            className="btn ghost"
            disabled={busy}
            onClick={() => run("archive")}
          >
            {t("review.archive")}
          </button>
        )}
        {st === "archived" && (
          <button type="button" className="btn" disabled={busy} onClick={() => run("restore")}>
            {t("review.restore")}
          </button>
        )}
        {!compact && (st === "rejected" || st === "archived") && (
          <DeleteVersion
            version={version}
            busy={busy}
            onConfirm={() => remove.mutate(version.id, { onSuccess: () => onDone?.("delete") })}
          />
        )}
      </div>
      {!compact && st === "published" && (
        <p className="muted" style={{ margin: 0, fontSize: 12 }}>
          {t("review.archiveBeforeDelete")}
        </p>
      )}
      {asking && (
        <form
          className={s.field}
          onSubmit={(e) => {
            e.preventDefault();
            run(asking, reason.trim());
          }}
        >
          <label className={s.field}>
            <span>
              {asking === "reject" ? t("review.rejectReason") : t("review.withdrawReason")}
            </span>
            <textarea
              className="input"
              value={reason}
              maxLength={1000}
              required={asking === "withdraw"}
              onChange={(e) => setReason(e.target.value)}
            />
          </label>
          <div className={s.actions}>
            <button
              type="submit"
              className={asking === "reject" ? "btn danger" : "btn"}
              disabled={busy || (asking === "withdraw" && !reason.trim())}
            >
              {asking === "reject" ? t("review.confirmReject") : t("review.confirmWithdraw")}
            </button>
            <button type="button" className="btn ghost" onClick={() => setAsking(null)}>
              {t("review.cancel")}
            </button>
          </div>
        </form>
      )}
      <ProblemText error={transition.error ?? remove.error} />
    </div>
  );
}

/** Permanent deletion after confirmation (FR-054, RULE-019): the file goes, the history and
 * the audit entry stay. */
function DeleteVersion({
  version,
  busy,
  onConfirm,
}: {
  version: Version;
  busy: boolean;
  onConfirm: () => void;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <button type="button" className="btn danger" disabled={busy}>
          {t("review.delete")}
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className={s.overlay} />
        <Dialog.Content className={s.dialog}>
          <Dialog.Title className="h-title">
            {t("review.deleteTitle", { n: version.number })}
          </Dialog.Title>
          <Dialog.Description>{t("review.deleteBody")}</Dialog.Description>
          <div className={s.actions}>
            <button
              type="button"
              className="btn danger"
              disabled={busy}
              onClick={() => {
                onConfirm();
                setOpen(false);
              }}
            >
              {t("review.deleteConfirm")}
            </button>
            <Dialog.Close asChild>
              <button type="button" className="btn ghost">
                {t("review.cancel")}
              </button>
            </Dialog.Close>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

/** FR-055: download the original or the processed file. */
export function Downloads({ version }: { version: Version }) {
  const { t } = useTranslation();
  if (version.state === "deleted") return null;
  return (
    <div className={s.actions}>
      <a className="btn ghost" href={fileUrl(version.id, "original", true)}>
        {t("review.downloadOriginal")}
      </a>
      {version.processing?.output && (
        <a className="btn ghost" href={fileUrl(version.id, "processed", true)}>
          {t("review.downloadProcessed")}
        </a>
      )}
    </div>
  );
}

function detail(details: Record<string, unknown>): string {
  const d = details as {
    expected?: unknown;
    actual?: unknown;
    problems?: unknown;
    white_edge?: unknown;
    max_kb?: unknown;
    bytes?: unknown;
  };
  if (d.expected !== undefined && d.actual !== undefined) {
    const show = (v: unknown) => (Array.isArray(v) ? v.join("×") : String(v));
    return `${show(d.actual)} ≠ ${show(d.expected)}`;
  }
  if (Array.isArray(d.problems) && d.problems.length) return d.problems.join(", ");
  if (typeof d.white_edge === "number") return `${Math.round(d.white_edge * 100)}%`;
  if (typeof d.max_kb === "number" && typeof d.bytes === "number") {
    return `${Math.round(d.bytes / 1024)} kB > ${d.max_kb} kB`;
  }
  return "";
}

/** Technical validation (FR-060): informative, never blocks a decision (RULE-009). */
export function ValidationPanel({ versionId }: { versionId: string }) {
  const { t } = useTranslation();
  const validation = useValidation(versionId);
  const data = validation.data;
  return (
    <section className={r.section} aria-labelledby={`val-${versionId}`}>
      <h3 className="h-panel" id={`val-${versionId}`}>
        {t("review.validation")}
      </h3>
      {data?.run_id && (
        <p className="muted" style={{ margin: 0, fontSize: 12 }}>
          {t("review.summary", data.summary)}
        </p>
      )}
      {!data?.results.length ? (
        <p className="muted" style={{ margin: 0 }}>
          {validation.isPending ? t("inputs.loading") : t("review.notValidated")}
        </p>
      ) : (
        <ul className={r.rules}>
          {data.results.map((res) => {
            const more = res.status === "failed" ? detail(res.details) : "";
            return (
              <li key={res.rule}>
                <span>{t(`review.rules.${res.rule}`, { defaultValue: res.rule })}</span>
                <span className={r[res.status]}>
                  {t(`review.status.${res.status}`)}
                  {more && <span className="muted"> · {more}</span>}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

/** The same file or a near-identical image elsewhere in the project (FR-059). */
export function DuplicatesPanel({ versionId }: { versionId: string }) {
  const { t } = useTranslation();
  const duplicates = useDuplicates(versionId);
  const rows = duplicates.data ?? [];
  if (!rows.length) return null;
  return (
    <section className={r.section} aria-labelledby={`dup-${versionId}`}>
      <h3 className="h-panel" id={`dup-${versionId}`}>
        {t("review.duplicates", { count: rows.length })}
      </h3>
      <ul className={r.versions}>
        {rows.map((d) => (
          <li key={d.version.id} className={s.row}>
            <Link to={`/library/${d.asset.id}`} className={s.grow}>
              {d.asset.name} v{d.version.number}
            </Link>
            <span className="muted" style={{ fontSize: 12 }}>
              {d.exact ? t("review.sameFile") : t("review.similar", { bits: d.distance })}
            </span>
            <Link className="btn ghost" to={`/review/compare?a=${versionId}&b=${d.version.id}`}>
              {t("library.compare")}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Comments from the user and from Claude (FR-061, FR-064). */
export function CommentsPanel({ versionId }: { versionId: string }) {
  const { t, i18n } = useTranslation();
  const comments = useComments(versionId);
  const add = useAddComment(versionId);
  const [body, setBody] = useState("");
  const time = new Intl.DateTimeFormat(i18n.language, { dateStyle: "short", timeStyle: "short" });
  const rows = comments.data ?? [];
  return (
    <section className={r.section} aria-labelledby={`com-${versionId}`}>
      <h3 className="h-panel" id={`com-${versionId}`}>
        {t("review.comments")}
      </h3>
      {rows.length ? (
        <ul className={r.comments}>
          {rows.map((c) => (
            <li key={c.id} className={r.comment} data-actor={c.actor}>
              <span className="muted" style={{ fontSize: 11, display: "block" }}>
                {c.actor === "mcp" ? t("review.claude") : t("review.you")} ·{" "}
                {time.format(new Date(c.at))}
              </span>
              {c.body}
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted" style={{ margin: 0 }}>
          {comments.isPending ? t("inputs.loading") : t("review.noComments")}
        </p>
      )}
      <form
        className={s.field}
        onSubmit={(e) => {
          e.preventDefault();
          if (body.trim()) add.mutate(body.trim(), { onSuccess: () => setBody("") });
        }}
      >
        <textarea
          className="input"
          value={body}
          maxLength={4000}
          aria-label={t("review.addComment")}
          placeholder={t("review.addComment")}
          onChange={(e) => setBody(e.target.value)}
        />
        <div className={s.actions}>
          <button type="submit" className="btn" disabled={!body.trim() || add.isPending}>
            {t("review.comment")}
          </button>
        </div>
      </form>
      <ProblemText error={add.error} />
    </section>
  );
}

const MAIN_PARAMS = ["prompt", "negative", "seed", "steps", "cfg", "sampler", "scheduler"];

/** The parameters the version was generated with (RULE-011). */
export function MetadataPanel({ version }: { version: Version }) {
  const { t } = useTranslation();
  const meta = version.generation_metadata as Record<string, unknown>;
  const models = meta.models as Record<string, { id?: string }> | undefined;
  const workflow = meta.workflow as { id?: string; version?: number } | undefined;
  const facts = MAIN_PARAMS.filter((k) => meta[k] != null && meta[k] !== "");
  return (
    <section className={r.section}>
      <h3 className="h-panel">{t("review.metadata")}</h3>
      {!facts.length && !models ? (
        <p className="muted" style={{ margin: 0 }}>
          {t("review.noMetadata")}
        </p>
      ) : (
        <dl className={s.facts}>
          {facts.map((k) => (
            <Fact key={k} term={t(`review.params.${k}`, { defaultValue: k })}>
              {String(meta[k])}
            </Fact>
          ))}
          {workflow?.id && (
            <Fact term={t("generation.workflow")}>
              {workflow.id} v{workflow.version ?? 1}
            </Fact>
          )}
          {models && (
            <Fact term={t("review.params.models")}>
              {Object.values(models)
                .map((m) => m.id)
                .filter(Boolean)
                .join(", ")}
            </Fact>
          )}
          {version.width != null && (
            <Fact term={t("review.params.size")}>
              {version.width}×{version.height}
            </Fact>
          )}
        </dl>
      )}
      <details>
        <summary className="muted">{t("review.allMetadata")}</summary>
        <pre className="mono" style={{ fontSize: 11, whiteSpace: "pre-wrap", margin: 0 }}>
          {JSON.stringify(version.generation_metadata, null, 2)}
        </pre>
      </details>
    </section>
  );
}

function Fact({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <>
      <dt>{term}</dt>
      <dd>{children}</dd>
    </>
  );
}
