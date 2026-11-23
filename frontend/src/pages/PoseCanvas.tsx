/** COCO-18 skeleton canvas: drag joints with a pointer or move them with the arrow keys
 * (FR-021). The joint order matches backend `poses/skeleton.py`. */
import { useRef } from "react";
import { useTranslation } from "react-i18next";

import type { Point } from "../api/library";
import s from "./workspace.module.css";

export const KEYPOINTS = [
  "nose",
  "neck",
  "right_shoulder",
  "right_elbow",
  "right_wrist",
  "left_shoulder",
  "left_elbow",
  "left_wrist",
  "right_hip",
  "right_knee",
  "right_ankle",
  "left_hip",
  "left_knee",
  "left_ankle",
  "right_eye",
  "left_eye",
  "right_ear",
  "left_ear",
] as const;
const LIMBS: [number, number][] = [
  [1, 2], [1, 5], [2, 3], [3, 4], [5, 6], [6, 7], [1, 8], [8, 9], [9, 10],
  [1, 11], [11, 12], [12, 13], [1, 0], [0, 14], [14, 16], [0, 15], [15, 17],
]; // prettier-ignore
const MIRROR = [0, 1, 5, 6, 7, 2, 3, 4, 11, 12, 13, 8, 9, 10, 15, 14, 17, 16];
// The usual OpenPose limb colours, so the skeleton reads like the ControlNet input.
const COLOURS = [
  "#ff0000", "#ff5500", "#ffaa00", "#ffff00", "#aaff00", "#55ff00", "#00ff00", "#00ff55",
  "#00ffaa", "#00ffff", "#00aaff", "#0055ff", "#0000ff", "#5500ff", "#aa00ff", "#ff00ff",
  "#ff00aa",
]; // prettier-ignore

export type Box = [number, number, number, number];

const clamp = (v: number) => Math.min(1, Math.max(0, Math.round(v * 10000) / 10000));

export function mirror(points: Point[]): Point[] {
  const out: Point[] = Array(KEYPOINTS.length).fill(null);
  points.forEach((p, i) => {
    out[MIRROR[i] ?? i] = p ? [clamp(1 - p[0]), p[1], p[2]] : null;
  });
  return out;
}

export function visibleCount(points: Point[]): number {
  return points.filter((p) => p !== null).length;
}

function Limbs({ points, w }: { points: Point[]; w: number }) {
  return (
    <>
      {LIMBS.map(([a, b], i) => {
        const pa = points[a];
        const pb = points[b];
        if (!pa || !pb) return null;
        return (
          <line
            key={i}
            x1={pa[0] * w}
            y1={pa[1] * 100}
            x2={pb[0] * w}
            y2={pb[1] * 100}
            stroke={COLOURS[i]}
            strokeWidth={1.6}
            strokeLinecap="round"
            opacity={0.85}
          />
        );
      })}
    </>
  );
}

/** Small read-only preview for the library list. */
export function PoseThumb({ points, aspect }: { points: (number[] | null)[]; aspect: number }) {
  const w = aspect * 100;
  return (
    <svg viewBox={`0 0 ${w} 100`} width={30 * aspect} height={30} aria-hidden="true">
      <rect width={w} height={100} fill="var(--surface-0)" />
      <Limbs points={points as Point[]} w={w} />
    </svg>
  );
}

export function PoseCanvas({
  aspect,
  points,
  onChange,
  selected,
  onSelect,
  background,
  drawBox,
  box,
  onBox,
}: {
  aspect: number;
  points: Point[];
  onChange: (points: Point[]) => void;
  selected: number | null;
  onSelect: (index: number | null) => void;
  background?: string | null;
  drawBox?: boolean;
  box?: Box | null;
  onBox?: (box: Box | null) => void;
}) {
  const { t } = useTranslation();
  const svg = useRef<SVGSVGElement>(null);
  const drag = useRef<{ joint: number } | { start: [number, number] } | null>(null);
  const w = aspect * 100;

  const toUnit = (e: React.PointerEvent): [number, number] | null => {
    const el = svg.current;
    const ctm = el?.getScreenCTM?.();
    if (!el || !ctm) return null;
    const pt = new DOMPoint(e.clientX, e.clientY).matrixTransform(ctm.inverse());
    return [clamp(pt.x / w), clamp(pt.y / 100)];
  };

  const move = (index: number, x: number, y: number) => {
    const next = points.slice();
    const old = next[index];
    next[index] = [clamp(x), clamp(y), old ? old[2] : 1];
    onChange(next);
  };

  const onPointerDown = (e: React.PointerEvent) => {
    if (!drawBox) return;
    const at = toUnit(e);
    if (!at) return;
    svg.current?.setPointerCapture?.(e.pointerId);
    drag.current = { start: at };
    onBox?.([at[0], at[1], at[0], at[1]]);
  };

  const onPointerMove = (e: React.PointerEvent) => {
    const d = drag.current;
    if (!d) return;
    const at = toUnit(e);
    if (!at) return;
    if ("joint" in d) {
      move(d.joint, at[0], at[1]);
    } else {
      const [x0, y0] = d.start;
      onBox?.([Math.min(x0, at[0]), Math.min(y0, at[1]), Math.max(x0, at[0]), Math.max(y0, at[1])]);
    }
  };

  const end = () => {
    const d = drag.current;
    drag.current = null;
    if (d && "start" in d && box && (box[2] - box[0] < 0.02 || box[3] - box[1] < 0.02)) {
      onBox?.(null); // a click, not a box
    }
  };

  const onKey = (index: number) => (e: React.KeyboardEvent) => {
    const p = points[index];
    if (!p) return;
    const step = e.shiftKey ? 0.05 : 0.01;
    const delta: Record<string, [number, number]> = {
      ArrowLeft: [-step, 0],
      ArrowRight: [step, 0],
      ArrowUp: [0, -step],
      ArrowDown: [0, step],
    };
    const d = delta[e.key];
    if (!d) return;
    e.preventDefault();
    move(index, p[0] + d[0], p[1] + d[1]);
  };

  return (
    <svg
      ref={svg}
      className={s.canvas}
      viewBox={`0 0 ${w} 100`}
      style={{ aspectRatio: `${aspect}`, cursor: drawBox ? "crosshair" : undefined }}
      role="group"
      aria-label={t("poses.canvas")}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={end}
      onPointerCancel={end}
    >
      {background && (
        <image href={background} width={w} height={100} preserveAspectRatio="none" opacity={0.55} />
      )}
      <Limbs points={points} w={w} />
      {box && (
        <rect
          x={box[0] * w}
          y={box[1] * 100}
          width={(box[2] - box[0]) * w}
          height={(box[3] - box[1]) * 100}
          fill="none"
          stroke="var(--accent)"
          strokeWidth={0.6}
          strokeDasharray="2 1"
        />
      )}
      {points.map((p, i) =>
        p ? (
          <g
            key={i}
            className={s.joint}
            tabIndex={drawBox ? -1 : 0}
            role="button"
            data-selected={selected === i}
            aria-label={t("poses.jointAt", {
              joint: t(`poses.joint.${KEYPOINTS[i]}`),
              x: Math.round(p[0] * 100),
              y: Math.round(p[1] * 100),
            })}
            onFocus={() => onSelect(i)}
            onKeyDown={onKey(i)}
            onPointerDown={(e) => {
              if (drawBox) return;
              e.stopPropagation();
              svg.current?.setPointerCapture?.(e.pointerId);
              drag.current = { joint: i };
              onSelect(i);
            }}
          >
            {/* A larger invisible target makes joints easy to grab on touch screens. */}
            <circle cx={p[0] * w} cy={p[1] * 100} r={3.2} fill="transparent" />
            <circle
              cx={p[0] * w}
              cy={p[1] * 100}
              r={1.3}
              fill={COLOURS[Math.min(i, COLOURS.length - 1)]}
              stroke="var(--surface-0)"
              strokeWidth={0.4}
            />
          </g>
        ) : null,
      )}
    </svg>
  );
}
