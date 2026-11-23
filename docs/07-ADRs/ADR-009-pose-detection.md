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
- DWPose itself is **not installed yet**: it needs ONNX Runtime, NumPy and Pillow in the worker image, plus the two model files (YOLOX-L and DW-LL). They are added only after the user approves them. Until then the job fails with `POSE_DETECTOR_NOT_INSTALLED` and the UI offers the editor.
