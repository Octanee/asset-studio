---
title: ADR-009 DWPose for pose detection
type: adr
status: proposed
created: 2026-11-22
updated: 2026-11-22
tags:
  - adr
---

# ADR-009: DWPose for pose detection

**Status:** proposed — decided at gate G-6.

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
