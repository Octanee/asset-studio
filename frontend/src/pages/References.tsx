/** References: upload with a role, filter by role, change role, detect a pose, remove
 * (FR-025, FR-026). */
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";

import {
  MAX_REFERENCE_BYTES,
  REFERENCE_ROLES,
  referenceFileUrl,
  useReferences,
  useUpdateReference,
  useUploadReference,
  type Reference,
  type ReferenceRole,
} from "../api/library";
import { useUi } from "../app/store";
import { NeedsProject, problemText, ProblemText } from "./common";
import s from "./workspace.module.css";

const ACCEPT = "image/png,image/jpeg,image/webp";

export function References() {
  const projectId = useUi((u) => u.projectId);
  if (!projectId) return <NeedsProject module="references" />;
  return <ReferenceBoard key={projectId} projectId={projectId} />;
}

function formatBytes(n: number): string {
  return n >= 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.ceil(n / 1024)} KB`;
}

function ReferenceBoard({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const [filter, setFilter] = useState<ReferenceRole | "all">("all");
  const [selected, setSelected] = useState<string | null>(null);
  const references = useReferences(projectId);
  const rows = (references.data ?? []).filter((r) => filter === "all" || r.role === filter);
  const current = references.data?.find((r) => r.id === selected);

  return (
    <div className={`${s.workspace} ${s.three}`}>
      <section className={`panel ${s.column}`} aria-label={t("references.filter")}>
        <span className="label">{t("references.filter")}</span>
        <ul className={s.list}>
          {(["all", ...REFERENCE_ROLES] as const).map((role) => {
            const count = (references.data ?? []).filter(
              (r) => role === "all" || r.role === role,
            ).length;
            return (
              <li key={role}>
                <button
                  type="button"
                  className={s.item}
                  aria-current={filter === role}
                  onClick={() => setFilter(role)}
                >
                  {role === "all" ? t("references.all") : t(`references.role.${role}`)}
                  <span className={`mono muted ${s.itemMeta}`}>{count}</span>
                </button>
              </li>
            );
          })}
        </ul>
      </section>
      <section className={`panel ${s.column}`} aria-label={t("nav.references")}>
        <Uploader projectId={projectId} defaultRole={filter === "all" ? "style" : filter} />
        {references.isPending ? (
          <p role="status" className="muted">
            {t("inputs.loading")}
          </p>
        ) : rows.length === 0 ? (
          <p className="muted" style={{ margin: 0 }}>
            {t("references.empty")}
          </p>
        ) : (
          <div className={s.tiles}>
            {rows.map((ref) => (
              <button
                key={ref.id}
                type="button"
                className={s.tile}
                aria-pressed={ref.id === selected}
                onClick={() => setSelected(ref.id)}
              >
                <img className={s.thumb} src={referenceFileUrl(ref.id)} alt="" loading="lazy" />
                <span className={s.name}>{ref.name}</span>
                <span className="mono muted">
                  {t(`references.role.${ref.role}`)} · {ref.width}×{ref.height}
                </span>
              </button>
            ))}
          </div>
        )}
      </section>
      <section className={`panel ${s.column}`} aria-label={t("references.details")}>
        {current ? (
          <Details
            key={current.id}
            projectId={projectId}
            reference={current}
            onRemoved={() => setSelected(null)}
          />
        ) : (
          <p className="muted" style={{ margin: 0 }}>
            {t("references.pick")}
          </p>
        )}
      </section>
    </div>
  );
}

function Uploader({ projectId, defaultRole }: { projectId: string; defaultRole: ReferenceRole }) {
  const { t } = useTranslation();
  const input = useRef<HTMLInputElement>(null);
  const [role, setRole] = useState<ReferenceRole>(defaultRole);
  const [over, setOver] = useState(false);
  const [failures, setFailures] = useState<string[]>([]);
  const upload = useUploadReference(projectId);

  const send = async (files: FileList | null) => {
    if (!files) return;
    const errors: string[] = [];
    for (const file of Array.from(files)) {
      try {
        await upload.mutateAsync({ file, role });
      } catch (error) {
        errors.push(`${file.name}: ${problemText(t, error)}`);
      }
    }
    setFailures(errors);
    if (input.current) input.current.value = "";
  };

  return (
    <div
      className={s.drop}
      data-over={over}
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        void send(e.dataTransfer.files);
      }}
    >
      <label className={s.field}>
        <span className="label">{t("references.uploadRole")}</span>
        <select
          className="input"
          value={role}
          onChange={(e) => setRole(e.target.value as ReferenceRole)}
        >
          {REFERENCE_ROLES.map((r) => (
            <option key={r} value={r}>
              {t(`references.role.${r}`)}
            </option>
          ))}
        </select>
      </label>
      <input
        ref={input}
        type="file"
        accept={ACCEPT}
        multiple
        className="visually-hidden"
        id="reference-upload"
        onChange={(e) => void send(e.target.files)}
      />
      <label htmlFor="reference-upload" className="btn primary">
        {upload.isPending ? t("references.uploading") : t("references.upload")}
      </label>
      <span className="muted" style={{ fontSize: 12 }}>
        {t("references.rules", { mb: MAX_REFERENCE_BYTES / 1024 / 1024 })}
      </span>
      {failures.length > 0 && (
        <ul role="alert" className={s.error} style={{ width: "100%", paddingLeft: 16 }}>
          {failures.map((f) => (
            <li key={f}>{f}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Details({
  projectId,
  reference,
  onRemoved,
}: {
  projectId: string;
  reference: Reference;
  onRemoved: () => void;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const update = useUpdateReference(projectId);
  const [confirm, setConfirm] = useState(false);

  return (
    <>
      <img className={s.preview} src={referenceFileUrl(reference.id)} alt={reference.name} />
      <h2 className="h-panel" style={{ wordBreak: "break-all" }}>
        {reference.name}
      </h2>
      <label className={s.field}>
        <span className="label">{t("references.roleLabel")}</span>
        <select
          className="input"
          value={reference.role}
          disabled={update.isPending}
          onChange={(e) =>
            update.mutate({ id: reference.id, role: e.target.value as ReferenceRole })
          }
        >
          {REFERENCE_ROLES.map((r) => (
            <option key={r} value={r}>
              {t(`references.role.${r}`)}
            </option>
          ))}
        </select>
      </label>
      <dl className="mono" style={{ margin: 0, display: "grid", gap: 4 }}>
        <div>
          {reference.width}×{reference.height} px · {formatBytes(reference.bytes)} ·{" "}
          {reference.mime.replace("image/", "").toUpperCase()}
        </div>
        <div className="muted" title={reference.sha256}>
          sha256 {reference.sha256.slice(0, 12)}…
        </div>
      </dl>
      <ProblemText error={update.error} />
      <div className={s.actions}>
        <button
          type="button"
          className="btn"
          onClick={() => void navigate(`/poses?reference=${reference.id}`)}
        >
          {t("references.detectPose")}
        </button>
        {confirm ? (
          <>
            <button
              type="button"
              className="btn danger"
              disabled={update.isPending}
              onClick={() =>
                update.mutate({ id: reference.id, archive: true }, { onSuccess: onRemoved })
              }
            >
              {t("references.remove")}
            </button>
            <button type="button" className="btn ghost" onClick={() => setConfirm(false)}>
              {t("styles.cancel")}
            </button>
          </>
        ) : (
          <button type="button" className="btn ghost" onClick={() => setConfirm(true)}>
            {t("references.remove")}
          </button>
        )}
      </div>
      {confirm && <p className="muted">{t("references.removeHint")}</p>}
    </>
  );
}
