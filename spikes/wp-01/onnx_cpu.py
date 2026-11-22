"""WP-01 / ADR-009, ADR-010: DWPose and BiRefNet with ONNX Runtime on CPU (worker container).

Usage: python onnx_cpu.py <models_dir> <images_dir> <out_dir>
Writes cut-outs (RGBA), pose overlays, and one JSON line of timings per model and image.
"""

import json
import sys
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image, ImageDraw

SO = ort.SessionOptions()
SO.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
PROV = ["CPUExecutionProvider"]


# ---------- BiRefNet ----------
def birefnet(sess: ort.InferenceSession, img: Image.Image) -> Image.Image:
    x = np.asarray(img.convert("RGB").resize((1024, 1024), Image.BILINEAR), dtype=np.float32) / 255.0
    x = (x - [0.485, 0.456, 0.406]) / [0.229, 0.224, 0.225]
    x = x.transpose(2, 0, 1)[None].astype(np.float32)
    out = sess.run(None, {sess.get_inputs()[0].name: x})[-1]
    mask = 1 / (1 + np.exp(-out[0, 0]))
    m = Image.fromarray((mask * 255).astype(np.uint8)).resize(img.size, Image.BILINEAR)
    rgba = img.convert("RGBA")
    rgba.putalpha(m)
    return rgba


# ---------- DWPose (YOLOX-L person detector + DW-LL whole-body pose) ----------
def _letterbox(img: np.ndarray, size: int = 640) -> tuple[np.ndarray, float]:
    r = min(size / img.shape[0], size / img.shape[1])
    resized = np.asarray(Image.fromarray(img).resize((int(img.shape[1] * r), int(img.shape[0] * r)), Image.BILINEAR))
    pad = np.full((size, size, 3), 114, dtype=np.uint8)
    pad[: resized.shape[0], : resized.shape[1]] = resized
    return pad, r


def detect_person(sess: ort.InferenceSession, rgb: np.ndarray) -> list[float] | None:
    pad, r = _letterbox(rgb[:, :, ::-1])  # YOLOX expects BGR, 0-255
    out = sess.run(None, {sess.get_inputs()[0].name: pad.transpose(2, 0, 1)[None].astype(np.float32)})[0][0]
    grids, strides = [], []
    for s in (8, 16, 32):
        h = w = 640 // s
        yv, xv = np.meshgrid(np.arange(h), np.arange(w), indexing="ij")
        grids.append(np.stack((xv, yv), 2).reshape(-1, 2))
        strides.append(np.full((h * w, 1), s))
    g, st = np.concatenate(grids), np.concatenate(strides)
    out[:, :2] = (out[:, :2] + g) * st
    out[:, 2:4] = np.exp(out[:, 2:4]) * st
    scores = out[:, 4] * out[:, 5]  # objectness * person class
    i = int(np.argmax(scores))
    if scores[i] < 0.3:
        return None
    cx, cy, w, h = out[i, :4] / r
    return [cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2, float(scores[i])]


def estimate_pose(sess: ort.InferenceSession, rgb: np.ndarray, box: list[float]) -> np.ndarray:
    x0, y0, x1, y1 = box[:4]
    cx, cy, w, h = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) * 1.25, (y1 - y0) * 1.25
    aspect = 288 / 384
    w, h = (h * aspect, h) if w / h < aspect else (w, w / aspect)
    crop = Image.fromarray(rgb).crop((int(cx - w / 2), int(cy - h / 2), int(cx + w / 2), int(cy + h / 2)))
    x = np.asarray(crop.resize((288, 384), Image.BILINEAR), dtype=np.float32)
    x = (x - [123.675, 116.28, 103.53]) / [58.395, 57.12, 57.375]
    sx, sy = sess.run(None, {sess.get_inputs()[0].name: x.transpose(2, 0, 1)[None].astype(np.float32)})
    kx, ky = sx[0].argmax(1) / 2.0, sy[0].argmax(1) / 2.0  # simcc split ratio 2
    conf = np.minimum(sx[0].max(1), sy[0].max(1))
    px = kx / 288 * w + (cx - w / 2)
    py = ky / 384 * h + (cy - h / 2)
    return np.stack([px, py, conf], 1)  # 133 whole-body keypoints


# COCO-WholeBody body indices -> OpenPose COCO-18 (neck = mid-shoulder)
OP18_FROM_WB = {0: 0, 2: 6, 3: 8, 4: 10, 5: 5, 6: 7, 7: 9, 8: 12, 9: 14, 10: 16, 11: 11, 12: 13,
                13: 15, 14: 2, 15: 1, 16: 4, 17: 3}
LIMBS = [(1, 2), (1, 5), (2, 3), (3, 4), (5, 6), (6, 7), (1, 8), (8, 9), (9, 10), (1, 11),
         (11, 12), (12, 13), (1, 0), (0, 14), (14, 16), (0, 15), (15, 17)]


def to_openpose18(wb: np.ndarray) -> dict[int, tuple[float, float, float]]:
    k = {op: tuple(wb[i]) for op, i in OP18_FROM_WB.items()}
    k[1] = tuple((wb[5] + wb[6]) / 2)
    return k


def main() -> None:
    models, images, out = (Path(a) for a in sys.argv[1:4])
    out.mkdir(parents=True, exist_ok=True)
    files = sorted(images.glob("*.png"))
    t = time.perf_counter()
    sessions = {name: ort.InferenceSession(str(models / f), SO, providers=PROV)
                for name, f in [("birefnet", "birefnet.onnx"), ("birefnet_lite", "birefnet_lite.onnx"),
                                ("yolox", "yolox_l.onnx"), ("dwpose", "dw-ll_ucoco_384.onnx")]}
    print(json.dumps({"load_seconds": round(time.perf_counter() - t, 2), "threads": ort.get_device()}), flush=True)
    for f in files:
        img = Image.open(f).convert("RGB")
        rgb = np.asarray(img)
        rec: dict[str, object] = {"image": f.name}
        for name in ("birefnet", "birefnet_lite"):
            t = time.perf_counter()
            cut = birefnet(sessions[name], img)
            rec[f"{name}_s"] = round(time.perf_counter() - t, 2)
            cut.save(out / f"{f.stem}.{name}.png")
        t = time.perf_counter()
        box = detect_person(sessions["yolox"], rgb)
        rec["detect_s"] = round(time.perf_counter() - t, 2)
        if box:
            t = time.perf_counter()
            wb = estimate_pose(sessions["dwpose"], rgb, box)
            rec["pose_s"] = round(time.perf_counter() - t, 2)
            k = to_openpose18(wb)
            rec["pose_mean_conf"] = round(float(np.mean([v[2] for v in k.values()])), 2)
            ov = img.copy()
            d = ImageDraw.Draw(ov)
            d.rectangle(box[:4], outline=(255, 0, 0), width=3)
            for a, b in LIMBS:
                if k[a][2] > 0.3 and k[b][2] > 0.3:
                    d.line([k[a][:2], k[b][:2]], fill=(0, 200, 255), width=6)
            ov.save(out / f"{f.stem}.pose.png")
        else:
            rec["pose_s"] = None
        print(json.dumps(rec), flush=True)


if __name__ == "__main__":
    main()
