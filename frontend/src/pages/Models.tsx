/** Models: registry with install state, approved downloads, checks and licence warnings
 * (FR-080-FR-084, RULE-007, RULE-008). */
import * as Dialog from "@radix-ui/react-dialog";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import {
  formatSize,
  MODEL_KINDS,
  useAcknowledgeLicence,
  useCancelJob,
  useDownload,
  useModelJobs,
  useModels,
  useRescan,
  useSetFamily,
  useVerify,
  type JobRow,
  type ModelKind,
  type ModelRow,
} from "../api/models";
import { useUi } from "../app/store";
import { ProblemText } from "./common";
import s from "./workspace.module.css";

const STATUS_CLASS: Record<string, string> = {
  installed: "s-approved",
  available: "s-archived",
  missing: "s-failed",
  downloading: "s-processing",
};
const CHECK_CLASS: Record<string, string> = {
  ok: "s-approved",
  unverified: "s-review",
  mismatch: "s-rejected",
};
const FAMILIES = ["sdxl", "sd15"];

/** The catalogue's placeholder licence is shown in the UI language. */
function licenceName(t: (key: string) => string, licence: ModelRow["licence"]): string {
  return licence.id === "unknown" ? t("models.licenceUnknown") : licence.name;
}

export function Models() {
  const { t } = useTranslation();
  const projectId = useUi((u) => u.projectId);
  const models = useModels(projectId);
  const active = useModelJobs();
  const rescan = useRescan();
  const [kind, setKind] = useState<ModelKind | "all">("all");
  const [downloading, setDownloading] = useState<ModelRow | null>(null);
  const [licence, setLicence] = useState<ModelRow | null>(null);
  const rows = (models.data ?? []).filter((m) => kind === "all" || m.kind === kind);
  const installed = (models.data ?? []).filter((m) => m.status === "installed").length;

  return (
    <section className={`panel ${s.column}`} aria-label={t("nav.models")}>
      <div className={s.header}>
        <div>
          <h2 className="h-panel">{t("models.title")}</h2>
          <p className="muted" style={{ margin: 0 }}>
            {t("models.summary", { installed, total: models.data?.length ?? 0 })}
          </p>
        </div>
        <button
          type="button"
          className="btn"
          disabled={rescan.isPending}
          onClick={() => rescan.mutate()}
        >
          {rescan.isPending ? t("models.scanning") : t("models.rescan")}
        </button>
      </div>
      {rescan.data && (
        <p role="status" className="muted" style={{ margin: 0 }}>
          {t("models.scanned", { added: rescan.data.added.length })}
        </p>
      )}
      <ProblemText error={rescan.error ?? models.error} />
      <div className={s.row} role="group" aria-label={t("models.kind")}>
        {(["all", ...MODEL_KINDS] as const).map((k) => (
          <button
            key={k}
            type="button"
            className="btn ghost"
            aria-pressed={kind === k}
            onClick={() => setKind(k)}
          >
            {k === "all" ? t("models.all") : t(`models.kinds.${k}`)}
          </button>
        ))}
      </div>
      {models.isPending ? (
        <p role="status" className="muted">
          {t("inputs.loading")}
        </p>
      ) : (
        <div className={s.tableWrap}>
          <table className={s.table}>
            <thead>
              <tr>
                <th scope="col">{t("models.name")}</th>
                <th scope="col">{t("models.family")}</th>
                <th scope="col">{t("models.licence")}</th>
                <th scope="col">{t("models.size")}</th>
                <th scope="col">{t("models.state")}</th>
                <th scope="col">
                  <span className="visually-hidden">{t("models.actions")}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((m) => (
                <Row
                  key={m.id}
                  model={m}
                  job={active.data?.[m.id]}
                  onDownload={() => setDownloading(m)}
                  onLicence={() => setLicence(m)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="muted" style={{ margin: 0, fontSize: 12 }}>
        {t("models.vramNote")}
      </p>
      {downloading && <DownloadDialog model={downloading} onClose={() => setDownloading(null)} />}
      {licence && projectId && (
        <LicenceDialog projectId={projectId} model={licence} onClose={() => setLicence(null)} />
      )}
    </section>
  );
}

function Progress({ job }: { job: JobRow }) {
  const { t } = useTranslation();
  const p = job.progress as { state?: string; bytes?: number; of?: number };
  const pct = p.of ? Math.floor(((p.bytes ?? 0) / p.of) * 100) : 0;
  const label =
    job.state === "queued"
      ? t("models.queued")
      : p.state === "verifying"
        ? t("models.verifying", { pct })
        : t("models.downloadingPct", { pct, of: formatSize(p.of) });
  return (
    <span className="mono" role="status">
      {label}
    </span>
  );
}

function Row({
  model: m,
  job,
  onDownload,
  onLicence,
}: {
  model: ModelRow;
  job?: JobRow;
  onDownload: () => void;
  onLicence: () => void;
}) {
  const { t } = useTranslation();
  const verify = useVerify();
  const cancel = useCancelJob();
  const setFamily = useSetFamily();
  const use = m.licence.commercial_use;

  return (
    <tr>
      <td>
        <div style={{ fontWeight: 500 }}>{m.name}</div>
        <div className="mono muted">
          {t(`models.kinds.${m.kind}`)} · {m.file_name}
        </div>
        {m.notes && (
          <div className="muted" style={{ fontSize: 12 }}>
            {m.notes}
          </div>
        )}
      </td>
      <td>
        {m.origin === "local" ? (
          <select
            className="input"
            aria-label={t("models.familyOf", { name: m.name })}
            value={m.family_id ?? ""}
            disabled={setFamily.isPending}
            onChange={(e) => setFamily.mutate({ modelId: m.id, familyId: e.target.value || null })}
          >
            <option value="">{t("models.familyUnknown")}</option>
            {FAMILIES.map((f) => (
              <option key={f} value={f}>
                {t(`models.families.${f}`)}
              </option>
            ))}
          </select>
        ) : m.family_id ? (
          t(`models.families.${m.family_id}`, { defaultValue: m.family_id })
        ) : (
          <span className="muted">{t("models.anyFamily")}</span>
        )}
      </td>
      <td>
        <div>{licenceName(t, m.licence)}</div>
        {use !== "allowed" && (
          <span className={`badge ${use === "forbidden" ? "s-rejected" : "s-review"}`}>
            <i />
            {t(`models.use.${use}`)}
          </span>
        )}
        {m.licence_conflict && (
          <div style={{ marginTop: 4 }}>
            {m.licence_acknowledged ? (
              <span className="badge s-approved">
                <i />
                {t("models.confirmed")}
              </span>
            ) : (
              <button type="button" className="btn ghost" onClick={onLicence}>
                {t("models.licenceWarning")}
              </button>
            )}
          </div>
        )}
      </td>
      <td className="mono">
        {formatSize(m.bytes ?? m.file_bytes)}
        {m.vram_mb && (
          <div className="muted">{t("models.vram", { gb: (m.vram_mb / 1024).toFixed(1) })}</div>
        )}
      </td>
      <td>
        <span className={`badge ${STATUS_CLASS[m.status] ?? ""}`}>
          <i />
          {t(`models.status.${m.status}`)}
        </span>
        {m.status === "installed" && (
          <div style={{ marginTop: 4 }}>
            <span className={`badge ${CHECK_CLASS[m.verification] ?? ""}`}>
              <i />
              {t(`models.check.${m.verification}`)}
            </span>
          </div>
        )}
        {job && (
          <div style={{ marginTop: 4 }}>
            <Progress job={job} />
          </div>
        )}
      </td>
      <td>
        <div className={s.actions}>
          {job ? (
            <button
              type="button"
              className="btn ghost"
              disabled={cancel.isPending}
              onClick={() => cancel.mutate(job.id)}
            >
              {t("models.cancel")}
            </button>
          ) : (
            <>
              {m.origin === "catalogue" &&
                (m.status === "available" || m.verification === "mismatch") && (
                  <button type="button" className="btn primary" onClick={onDownload}>
                    {t("models.download")}
                  </button>
                )}
              {m.status === "installed" && (
                <button
                  type="button"
                  className="btn ghost"
                  disabled={verify.isPending}
                  onClick={() => verify.mutate(m.id)}
                >
                  {t("models.verify")}
                </button>
              )}
            </>
          )}
        </div>
        <ProblemText error={verify.error ?? cancel.error ?? setFamily.error} />
      </td>
    </tr>
  );
}

function DownloadDialog({ model, onClose }: { model: ModelRow; onClose: () => void }) {
  const { t } = useTranslation();
  const download = useDownload();
  return (
    <Dialog.Root open onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className={s.overlay} />
        <Dialog.Content className={s.dialog}>
          <Dialog.Title className="h-panel">
            {t("models.confirmTitle", { name: model.name })}
          </Dialog.Title>
          <Dialog.Description className="muted">{t("models.confirmBody")}</Dialog.Description>
          <dl className={s.facts}>
            <dt>{t("models.file")}</dt>
            <dd className="mono">{model.file_name}</dd>
            <dt>{t("models.source")}</dt>
            <dd className="mono" style={{ wordBreak: "break-all" }}>
              {model.source_url}
            </dd>
            <dt>{t("models.size")}</dt>
            <dd className="mono">{formatSize(model.bytes)}</dd>
            <dt>{t("models.licence")}</dt>
            <dd>
              {licenceName(t, model.licence)}
              {model.licence.notes && <div className="muted">{model.licence.notes}</div>}
            </dd>
            <dt>SHA-256</dt>
            <dd className="mono" style={{ wordBreak: "break-all" }}>
              {model.sha256}
            </dd>
          </dl>
          <ProblemText error={download.error} />
          <div className={s.actions} style={{ justifyContent: "flex-end" }}>
            <Dialog.Close className="btn ghost">{t("styles.cancel")}</Dialog.Close>
            <button
              type="button"
              className="btn primary"
              disabled={download.isPending}
              onClick={() => download.mutate(model, { onSuccess: onClose })}
            >
              {t("models.confirmDownload", { size: formatSize(model.bytes) })}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function LicenceDialog({
  projectId,
  model,
  onClose,
}: {
  projectId: string;
  model: ModelRow;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const ack = useAcknowledgeLicence(projectId);
  const [understood, setUnderstood] = useState(false);
  const [note, setNote] = useState("");
  return (
    <Dialog.Root open onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className={s.overlay} />
        <Dialog.Content className={s.dialog}>
          <Dialog.Title className="h-panel">
            {t("models.licenceTitle", { name: model.name })}
          </Dialog.Title>
          <Dialog.Description>
            {t("models.licenceBody", {
              licence: licenceName(t, model.licence),
              use: t(`models.use.${model.licence.commercial_use}`),
            })}
          </Dialog.Description>
          {model.licence.url && (
            <a href={model.licence.url} target="_blank" rel="noreferrer noopener">
              {t("models.readLicence")}
            </a>
          )}
          <label className={s.field}>
            <span className="label">{t("models.note")}</span>
            <input
              className="input"
              maxLength={500}
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </label>
          <label className={s.row}>
            <input
              type="checkbox"
              checked={understood}
              onChange={(e) => setUnderstood(e.target.checked)}
            />
            {t("models.understand")}
          </label>
          <ProblemText error={ack.error} />
          <div className={s.actions} style={{ justifyContent: "flex-end" }}>
            <Dialog.Close className="btn ghost">{t("styles.cancel")}</Dialog.Close>
            <button
              type="button"
              className="btn danger"
              disabled={!understood || ack.isPending}
              onClick={() => ack.mutate({ modelId: model.id, note }, { onSuccess: onClose })}
            >
              {t("models.confirmUse")}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
