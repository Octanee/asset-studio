---
title: ADR-009 DWPose for pose detection
type: adr
status: accepted
created: 2026-11-22
updated: 2026-11-23
tags:
  - adr
---

# ADR-009: DWPose for pose detection

**Status:** accepted at gate G-6 (2026-11-22, D-46).

## Context
D-23 needs pose detection from images. R-19: the original OpenPose (CMU) licence is non-commercial.

## Decision
DWPose (YOLOX detector + DW-LL whole-body model, ONNX), run with ONNX Runtime on CPU in the worker. Its output is converted to COCO-18 keypoints for the pose editor and ControlNet.

## Alternatives considered

| Option | Advantages | Disadvantages |
|---|---|---|
| CMU OpenPose | reference implementation | non-commercial licence |
| MediaPipe Pose | Apache-2.0, fast | different keypoint set; weaker for full-body side views |

## Consequences
The code is reported as Apache-2.0 (via mmpose). **Verify the upstream LICENSE and model-card terms in WP-01** before enabling it; record them in the model catalogue.

## Implementation notes (WP-07)

- Detection runs as a `detect_pose` job on the CPU lane (`modules/poses/service.py`). The job only **proposes** a skeleton; the user checks it in the editor and saves it as a pose with `source = 'detected'` and a link to the reference (AC-011).
- The detector is pluggable (`modules/poses/detection.py`, `PoseDetector`). The user can draw a box around the figure; the box skips the person detector (the manual fallback from the WP-01 spike, where one standing figure was missed).
- DWPose (`modules/poses/dwpose.py`) runs with ONNX Runtime, NumPy and Pillow, added to the backend image with the user's approval (2026-11-23). The two model files (`yolox_l.onnx`, `dw-ll_ucoco_384.onnx` from `yzd-v/DWPose`) are installed into `<data>/models/pose` by `python -m asset_studio.modules.poses.install`, which checks their SHA-256; the detector checks them again before loading. Without them the job fails with `POSE_DETECTOR_NOT_INSTALLED` and the UI offers the editor.
- Thresholds: person 0.2 (the spike missed a figure at 0.3), joint 0.3 (weaker joints are left for the user to add).
- Measured on the WP-01 images (native CPU): 5 of 6 figures found with 17–18 joints in 0.6–0.8 s each; the missed figure (person score 0.10) gives 18 joints at mean confidence 0.74 with a drawn box. The models load once per worker and stay loaded.
