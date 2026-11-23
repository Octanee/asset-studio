/** Poses: library (built-in and project), skeleton editor, detection from an image
 * (FR-020, FR-021, FR-022, AC-011). */
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router";

import { ApiError } from "../api/client";
import {
  POSE_VIEWS,
  referenceFileUrl,
  useArchive,
  useDetectPose,
  useJob,
  usePoses,
  useReferences,
  useSavePose,
  type Point,
  type PoseRow,
  type PoseView,
} from "../api/library";
import { useUi } from "../app/store";
import { ProblemText } from "./common";
import { KEYPOINTS, mirror, PoseCanvas, PoseThumb, visibleCount, type Box } from "./PoseCanvas";
import s from "./workspace.module.css";

const MIN_JOINTS = 4;

interface Draft {
  id?: string;
  builtin: boolean;
  name: string;
  view: PoseView;
  aspect: number;
  keypoints: Point[];
  sourceReferenceId: string | null;
}

function draftOf(pose: PoseRow): Draft {
  return {
    id: pose.id,
    builtin: pose.project_id === null,
    name: pose.name,
    view: pose.view as PoseView,
    aspect: pose.aspect,
    keypoints: pose.keypoints as Point[],
    sourceReferenceId: pose.source_reference_id,
  };
}

export function Poses() {
  const { t } = useTranslation();
  const projectId = useUi((u) => u.projectId);
  const poses = usePoses(projectId);
  const [params, setParams] = useSearchParams();
  const [draft, setDraft] = useState<Draft | null>(null);
  const [selectedJoint, setSelectedJoint] = useState<number | null>(null);
  const [background, setBackground] = useState<string | null>(null);
  const last = useRef<Record<number, Point>>({});

  // Start on the first library pose.
  useEffect(() => {
    const first = poses.data?.[0];
    if (!draft && first) setDraft(draftOf(first));
  }, [draft, poses.data]);

  const open = (pose: PoseRow) => {
    setDraft(draftOf(pose));
    setSelectedJoint(null);
    setBackground(pose.source_reference_id ? referenceFileUrl(pose.source_reference_id) : null);
  };

  const builtin = (poses.data ?? []).filter((p) => p.project_id === null);
  const own = (poses.data ?? []).filter((p) => p.project_id !== null);

  return (
    <div className={`${s.workspace} ${s.three}`}>
      <section className={`panel ${s.column}`} aria-label={t("poses.library")}>
        {(
          [
            ["builtin", builtin],
            ["project", own],
          ] as const
        ).map(([group, rows]) => (
          <div key={group} className={s.field}>
            <span className="label">{t(`poses.group.${group}`)}</span>
            {rows.length === 0 ? (
              <span className="muted">
                {projectId ? t("poses.noProjectPoses") : t("inputs.needsProject")}
              </span>
            ) : (
              <ul className={s.list}>
                {rows.map((pose) => (
                  <li key={pose.id}>
                    <button
                      type="button"
                      className={s.item}
                      aria-current={draft?.id === pose.id}
                      onClick={() => open(pose)}
                    >
                      <PoseThumb points={pose.keypoints} aspect={pose.aspect} />
                      <span className={s.name}>{pose.name}</span>
                      <span className={`muted ${s.itemMeta}`} style={{ fontSize: 12 }}>
                        {t(`poses.view.${pose.view}`)}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </section>
      <section className={`panel ${s.column}`} aria-label={t("poses.editor")}>
        {draft ? (
          <Editor
            key={draft.id ?? "new"}
            draft={draft}
            setDraft={setDraft}
            projectId={projectId}
            selectedJoint={selectedJoint}
            setSelectedJoint={setSelectedJoint}
            background={background}
            last={last}
            onArchived={() => setDraft(null)}
          />
        ) : (
          <p role="status" className="muted">
            {t("inputs.loading")}
          </p>
        )}
      </section>
      <section className={`panel ${s.column}`} aria-label={t("poses.detect")}>
        {projectId ? (
          <Detect
            projectId={projectId}
            initialReference={params.get("reference")}
            onBackground={setBackground}
            onDetected={(result) => {
              setDraft({
                builtin: false,
                name: t("poses.detectedName"),
                view: "front",
                aspect: result.aspect,
                keypoints: result.keypoints,
                sourceReferenceId: result.referenceId,
              });
              setSelectedJoint(null);
              setParams({}, { replace: true });
            }}
          />
        ) : (
          <p className="muted" style={{ margin: 0 }}>
            {t("inputs.needsProject")}
          </p>
        )}
      </section>
    </div>
  );
}

function Editor({
  draft,
  setDraft,
  projectId,
  selectedJoint,
  setSelectedJoint,
  background,
  last,
  onArchived,
}: {
  draft: Draft;
  setDraft: (d: Draft) => void;
  projectId: string | null;
  selectedJoint: number | null;
  setSelectedJoint: (i: number | null) => void;
  background: string | null;
  last: React.MutableRefObject<Record<number, Point>>;
  onArchived: () => void;
}) {
  const { t } = useTranslation();
  const save = useSavePose(projectId ?? "");
  const archive = useArchive(projectId ?? "");
  const [saved, setSaved] = useState(false);
  const update = (patch: Partial<Draft>) => {
    setSaved(false);
    setDraft({ ...draft, ...patch });
  };
  const visible = visibleCount(draft.keypoints);
  const blocked = !projectId
    ? t("inputs.needsProject")
    : visible < MIN_JOINTS
      ? t("poses.tooFew", { n: MIN_JOINTS })
      : !draft.name.trim()
        ? t("poses.needsName")
        : null;

  const toggle = (i: number, on: boolean) => {
    const next = draft.keypoints.slice();
    if (on) {
      next[i] = last.current[i] ?? [0.5, 0.5, 1];
    } else {
      last.current[i] = next[i] ?? null;
      next[i] = null;
    }
    update({ keypoints: next });
  };

  const submit = (asNew: boolean) =>
    save.mutate(
      {
        id: asNew || draft.builtin ? undefined : draft.id,
        name: draft.name,
        view: draft.view,
        aspect: draft.aspect,
        keypoints: draft.keypoints,
        // Ignored by updates; a new pose keeps the image it was detected from.
        sourceReferenceId: draft.sourceReferenceId,
      },
      {
        onSuccess: (pose) => {
          setSaved(true);
          setDraft(draftOf(pose));
        },
      },
    );

  return (
    <>
      <div className={s.header}>
        <h2 className="h-panel">{draft.name || t("poses.untitled")}</h2>
        <span className="muted" style={{ fontSize: 12 }}>
          {draft.builtin
            ? t("poses.builtinNote")
            : draft.sourceReferenceId
              ? t("poses.fromImage")
              : null}
        </span>
      </div>
      <PoseCanvas
        aspect={draft.aspect}
        points={draft.keypoints}
        onChange={(keypoints) => update({ keypoints })}
        selected={selectedJoint}
        onSelect={setSelectedJoint}
        background={background}
      />
      <p className="muted" style={{ margin: 0, fontSize: 12 }}>
        {t("poses.keyboard")}
      </p>
      <div className={s.row}>
        <label className={`${s.field} ${s.grow}`}>
          <span className="label">{t("poses.name")}</span>
          <input
            className="input"
            maxLength={120}
            value={draft.name}
            onChange={(e) => update({ name: e.target.value })}
          />
        </label>
        <label className={s.field}>
          <span className="label">{t("poses.viewLabel")}</span>
          <select
            className="input"
            value={draft.view}
            onChange={(e) => update({ view: e.target.value as PoseView })}
          >
            {POSE_VIEWS.map((v) => (
              <option key={v} value={v}>
                {t(`poses.view.${v}`)}
              </option>
            ))}
          </select>
        </label>
      </div>
      <fieldset className={s.field} style={{ border: 0, padding: 0, margin: 0 }}>
        <legend className="label">{t("poses.joints", { visible, total: KEYPOINTS.length })}</legend>
        <div className={s.joints}>
          {KEYPOINTS.map((name, i) => (
            <label key={name}>
              <input
                type="checkbox"
                checked={draft.keypoints[i] !== null}
                onChange={(e) => toggle(i, e.target.checked)}
              />
              {t(`poses.joint.${name}`)}
            </label>
          ))}
        </div>
      </fieldset>
      <ProblemText error={save.error ?? archive.error} />
      {saved && (
        <p role="status" className="muted" style={{ margin: 0 }}>
          {t("poses.saved")}
        </p>
      )}
      <div className={s.actions}>
        <button
          type="button"
          className="btn"
          onClick={() => update({ keypoints: mirror(draft.keypoints) })}
        >
          {t("poses.mirror")}
        </button>
        <button
          type="button"
          className="btn primary"
          disabled={!!blocked || save.isPending}
          onClick={() => submit(false)}
        >
          {draft.builtin ? t("poses.saveCopy") : t("poses.save")}
        </button>
        {draft.id && !draft.builtin && (
          <>
            <button
              type="button"
              className="btn"
              disabled={!!blocked || save.isPending}
              onClick={() => submit(true)}
            >
              {t("poses.saveAsNew")}
            </button>
            <button
              type="button"
              className="btn ghost"
              disabled={archive.isPending}
              onClick={() =>
                draft.id &&
                archive.mutate({ kind: "pose", id: draft.id }, { onSuccess: onArchived })
              }
            >
              {t("styles.archive")}
            </button>
          </>
        )}
      </div>
      {blocked && (
        <p className="muted" style={{ margin: 0 }}>
          {blocked}
        </p>
      )}
    </>
  );
}

interface DetectResult {
  referenceId: string;
  aspect: number;
  keypoints: Point[];
}

function Detect({
  projectId,
  initialReference,
  onBackground,
  onDetected,
}: {
  projectId: string;
  initialReference: string | null;
  onBackground: (url: string | null) => void;
  onDetected: (result: DetectResult) => void;
}) {
  const { t } = useTranslation();
  const references = useReferences(projectId);
  // Pose references first: they are the usual source.
  const rows = [...(references.data ?? [])].sort(
    (a, b) => Number(b.role === "pose") - Number(a.role === "pose"),
  );
  const [referenceId, setReferenceId] = useState<string | null>(initialReference);
  const [jobId, setJobId] = useState<string | null>(null);
  const [drawing, setDrawing] = useState(false);
  const [box, setBox] = useState<Box | null>(null);
  const detect = useDetectPose();
  const job = useJob(jobId);
  const handled = useRef<string | null>(null);
  const reference = rows.find((r) => r.id === referenceId);

  useEffect(() => {
    const j = job.data;
    if (!j || j.state !== "completed" || handled.current === j.id) return;
    handled.current = j.id;
    const result = j.result as { aspect: number; keypoints: Point[]; reference_id: string };
    onDetected({
      referenceId: result.reference_id,
      aspect: result.aspect,
      keypoints: result.keypoints,
    });
    onBackground(referenceFileUrl(result.reference_id));
  }, [job.data, onBackground, onDetected]);

  const run = () => {
    if (!referenceId) return;
    handled.current = null;
    detect.mutate(
      { referenceId, box: drawing ? box : null },
      { onSuccess: (queued) => setJobId(queued.id) },
    );
  };

  const state = job.data?.state;
  const busy = detect.isPending || state === "queued" || state === "running";
  const failure = job.data?.state === "failed" ? job.data.error : null;

  return (
    <>
      <h2 className="h-panel">{t("poses.detect")}</h2>
      <p className="muted" style={{ margin: 0 }}>
        {t("poses.detectHint")}
      </p>
      {rows.length === 0 ? (
        <p className="muted" style={{ margin: 0 }}>
          {t("poses.noReferences")}
        </p>
      ) : (
        <div className={`${s.tiles} ${s.small}`}>
          {rows.map((ref) => (
            <button
              key={ref.id}
              type="button"
              className={s.tile}
              aria-pressed={ref.id === referenceId}
              onClick={() => {
                setReferenceId(ref.id);
                setBox(null);
              }}
            >
              <img className={s.thumb} src={referenceFileUrl(ref.id)} alt="" loading="lazy" />
              <span className={s.name}>{ref.name}</span>
            </button>
          ))}
        </div>
      )}
      {reference && drawing && (
        <>
          <PoseCanvas
            aspect={reference.width / reference.height}
            points={[]}
            onChange={() => undefined}
            selected={null}
            onSelect={() => undefined}
            background={referenceFileUrl(reference.id)}
            drawBox
            box={box}
            onBox={setBox}
          />
          <span className="muted" style={{ fontSize: 12 }}>
            {box ? t("poses.boxReady") : t("poses.boxHint")}
          </span>
        </>
      )}
      <div className={s.actions}>
        <button
          type="button"
          className="btn primary"
          disabled={!referenceId || busy || (drawing && !box)}
          onClick={run}
        >
          {busy ? t("poses.detecting") : drawing ? t("poses.detectInBox") : t("poses.detect")}
        </button>
        <button
          type="button"
          className="btn ghost"
          aria-pressed={drawing}
          disabled={!reference}
          onClick={() => {
            setDrawing(!drawing);
            setBox(null);
          }}
        >
          {t("poses.drawBox")}
        </button>
      </div>
      {state === "queued" && job.data?.wait_reason && (
        <p className="muted">{t("poses.waiting", { reason: job.data.wait_reason })}</p>
      )}
      <ProblemText error={detect.error} />
      {failure && (
        <ProblemText
          error={
            new ApiError({
              status: 0,
              code: String(failure.code ?? "JOB_FAILED"),
              detail: String(failure.message ?? ""),
            })
          }
        />
      )}
      {failure && <p className="muted">{t("poses.manualFallback")}</p>}
    </>
  );
}
