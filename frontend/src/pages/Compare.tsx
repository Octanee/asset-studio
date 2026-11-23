/** Compare two versions (FR-058): side by side, swipe or overlay with a linked zoom and pan,
 * a parameter diff, and the review decision for each (WP-10). */
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router";

import {
  fileUrl,
  metadataDiff,
  useAssetDetail,
  useVersionDetail,
  type VersionDetail,
} from "../api/review";
import { ProblemText } from "./common";
import { StateBadge, VersionActions } from "./ReviewParts";
import r from "./review.module.css";
import s from "./workspace.module.css";

const MODES = ["side", "swipe", "overlay"] as const;
type Mode = (typeof MODES)[number];

interface View {
  zoom: number;
  x: number;
  y: number;
}

export function Compare() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const aId = params.get("a");
  const bId = params.get("b");
  const a = useVersionDetail(aId);
  const b = useVersionDetail(bId);

  if (!aId || !bId) {
    return (
      <section className={`panel ${s.column}`}>
        <h2 className="h-title">{t("compare.title")}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {t("compare.choose")} <Link to="/library">{t("review.openLibrary")}</Link>
        </p>
      </section>
    );
  }
  if (a.isPending || b.isPending) {
    return (
      <p role="status" className="muted">
        {t("inputs.loading")}
      </p>
    );
  }
  if (!a.data || !b.data) {
    return (
      <section className={`panel ${s.column}`}>
        <ProblemText error={a.error ?? b.error} />
      </section>
    );
  }
  return (
    <Comparison
      a={a.data}
      b={b.data}
      onSwap={() => setParams({ a: bId, b: aId }, { replace: true })}
    />
  );
}

function src(v: VersionDetail): string {
  return fileUrl(v.id, v.processing?.output ? "processed" : "original");
}

function Comparison({ a, b, onSwap }: { a: VersionDetail; b: VersionDetail; onSwap: () => void }) {
  const { t } = useTranslation();
  const [mode, setMode] = useState<Mode>("side");
  const [view, setView] = useState<View>({ zoom: 1, x: 0, y: 0 });
  const [split, setSplit] = useState(50);
  const [opacity, setOpacity] = useState(50);
  const [onlyChanges, setOnlyChanges] = useState(true);
  const drag = useRef<{ x: number; y: number } | null>(null);
  const assetA = useAssetDetail(a.asset_id);
  const assetB = useAssetDetail(b.asset_id);
  const twoAssets = a.asset_id !== b.asset_id;
  const labelA = `${twoAssets && assetA.data ? `${assetA.data.name} ` : ""}v${a.number}`;
  const labelB = `${twoAssets && assetB.data ? `${assetB.data.name} ` : ""}v${b.number}`;
  const pairs: [VersionDetail, string][] = [
    [a, labelA],
    [b, labelB],
  ];

  const transform = `translate(${view.x}px, ${view.y}px) scale(${view.zoom})`;
  // One pan for both images, so they stay aligned (linked zoom).
  const pan = {
    onPointerDown: (e: React.PointerEvent<HTMLDivElement>) => {
      drag.current = { x: e.clientX - view.x, y: e.clientY - view.y };
      e.currentTarget.setPointerCapture(e.pointerId);
    },
    onPointerMove: (e: React.PointerEvent<HTMLDivElement>) => {
      const from = drag.current;
      if (from) setView((v) => ({ ...v, x: e.clientX - from.x, y: e.clientY - from.y }));
    },
    onPointerUp: () => {
      drag.current = null;
    },
  };
  const layer = (v: VersionDetail, style: React.CSSProperties = {}) => (
    <img
      className={r.layer}
      src={src(v)}
      alt={t("compare.imageAlt", { n: v.number })}
      draggable={false}
      style={{ transform, ...style }}
    />
  );
  const diff = metadataDiff(a.generation_metadata, b.generation_metadata);
  const shown = onlyChanges ? diff.filter((d) => !d.same) : diff;

  return (
    <section className={s.stack} aria-label={t("compare.title")}>
      <div className={`panel ${s.column}`}>
        <div className={s.header}>
          <div className={s.row} role="group" aria-label={t("compare.mode")}>
            {MODES.map((m) => (
              <button
                key={m}
                type="button"
                className="btn ghost"
                aria-pressed={mode === m}
                onClick={() => setMode(m)}
              >
                {t(`compare.modes.${m}`)}
              </button>
            ))}
          </div>
          <div className={s.actions}>
            <label className={s.radio}>
              <span className="muted">{t("compare.zoom")}</span>
              <input
                type="range"
                min={1}
                max={8}
                step={0.25}
                value={view.zoom}
                onChange={(e) => setView((v) => ({ ...v, zoom: Number(e.target.value) }))}
              />
              <span className="mono">{view.zoom.toFixed(2)}×</span>
            </label>
            <button
              type="button"
              className="btn ghost"
              onClick={() => setView({ zoom: 1, x: 0, y: 0 })}
            >
              {t("compare.reset")}
            </button>
            <button type="button" className="btn ghost" onClick={onSwap}>
              {t("compare.swap")}
            </button>
          </div>
        </div>

        {mode === "side" && (
          <div className={r.sides}>
            {pairs.map(([v, text]) => (
              <div key={v.id} className={r.viewport} {...pan}>
                <span className={r.label} style={{ left: 8 }}>
                  {text}
                </span>
                {layer(v)}
              </div>
            ))}
          </div>
        )}
        {mode === "swipe" && (
          <>
            <div className={r.viewport} {...pan}>
              <span className={r.label} style={{ left: 8 }}>
                {labelA}
              </span>
              <span className={r.label} style={{ right: 8 }}>
                {labelB}
              </span>
              {layer(a)}
              <div style={{ position: "absolute", inset: 0, clipPath: `inset(0 0 0 ${split}%)` }}>
                {layer(b)}
              </div>
              <span className={r.divider} style={{ left: `${split}%` }} />
            </div>
            <label className={s.field}>
              <span className="muted">{t("compare.split")}</span>
              <input
                type="range"
                min={0}
                max={100}
                value={split}
                onChange={(e) => setSplit(Number(e.target.value))}
              />
            </label>
          </>
        )}
        {mode === "overlay" && (
          <>
            <div className={r.viewport} {...pan}>
              <span className={r.label} style={{ left: 8 }}>
                {labelA} + {labelB}
              </span>
              {layer(a)}
              {layer(b, { opacity: opacity / 100 })}
            </div>
            <label className={s.field}>
              <span className="muted">{t("compare.opacity", { label: labelB })}</span>
              <input
                type="range"
                min={0}
                max={100}
                value={opacity}
                onChange={(e) => setOpacity(Number(e.target.value))}
              />
            </label>
          </>
        )}
      </div>

      <div className={r.sides}>
        {pairs.map(([v, text]) => (
          <div key={v.id} className={`panel ${s.column}`}>
            <div className={s.header}>
              <Link to={`/library/${v.asset_id}`} className="h-panel">
                {text}
              </Link>
              <StateBadge state={v.state} />
            </div>
            <VersionActions version={v} compact />
          </div>
        ))}
      </div>

      <div className={`panel ${s.column}`}>
        <div className={s.header}>
          <h2 className="h-panel" style={{ margin: 0 }}>
            {t("compare.parameters")}
          </h2>
          <label className={s.radio}>
            <input
              type="checkbox"
              checked={onlyChanges}
              onChange={(e) => setOnlyChanges(e.target.checked)}
            />
            {t("compare.onlyChanges")}
          </label>
        </div>
        {!shown.length ? (
          <p className="muted" style={{ margin: 0 }}>
            {t("compare.noChanges")}
          </p>
        ) : (
          <div className={s.tableWrap}>
            <table className={`${s.table} ${r.diff}`}>
              <thead>
                <tr>
                  <th scope="col">{t("compare.parameter")}</th>
                  <th scope="col">{labelA}</th>
                  <th scope="col">{labelB}</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((d) => (
                  <tr key={d.key} data-same={d.same}>
                    <td>{d.key}</td>
                    <td>{d.a}</td>
                    <td>{d.b}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
