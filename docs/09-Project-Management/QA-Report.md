---
title: QA Report
type: project-management
status: draft
created: 2026-11-24
updated: 2026-11-24
tags:
  - qa
  - acceptance
---

# QA Report (WP-18)

The MVP was installed and run on the reference machine (Windows 11, a 6 GB NVIDIA laptop GPU, Docker Desktop) with the scripts from WP-17:
- `asset-studio.cmd setup` then `start`;
- ComfyUI v0.46.0 and kohya from the pinned installs;
- models: SDXL base 1.0, the xinsir OpenPose ControlNet for SDXL, SDXL VAE fp16-fix.

Every criterion is listed in [[Acceptance-Coverage]] with its automated tests. This page records the live run of 2026-11-24.

## Results

| AC | Live result | Evidence |
|---|---|---|
| AC-001 | ✅ | See the AC-001 section below. |
| AC-005 | ✅ | 3 generations queued; `api`, `worker` and `web` restarted while the first one ran. The two queued jobs kept their state and history and completed. The running one became `interrupted` with its events kept; a retry through the API completed it on attempt 2 (`queued → started → interrupted → retried → started → completed`). |
| AC-006 | ✅ | The engine was stopped from the app. The generation check reported `ENGINE_UNAVAILABLE`, and a queued generation waited with that reason. Meanwhile an SVG badge was ready for review in 2.0 s, and was approved and exported; the library listed every asset. After the engine started again, the waiting generation completed on its own. |
| AC-007 | ✅ (WP-13) | SD1.5 LoRA on 10 images in 6 min 45 s, then used in a generation. The SDXL estimate warns first. |
| AC-009 | ✅ (WP-16) | Backup, wipe, restore into an empty stack. |
| AC-014 | ✅ after a fix | See the AC-014 section below. |
| AC-015 | ✅ | All six ports listen on `127.0.0.1` only: web 8480, API 8400, MCP 8411, database 5433, host agent 8410, ComfyUI 8188. Connections to them through the machine's network address are refused; through loopback they work. |

The other criteria (AC-002, 003, 004, 008, 010, 011, 012, 013) do not depend on the GPU. Their automated tests cover them, and earlier live checks are noted in [[Acceptance-Coverage]].

### AC-001

**Setup:**
- 10 exercises, one style (flat vector, palette) and one character.
- Each exercise had its own pose: the 5 built-in poses, plus 5 poses made through the pose API.
- 768 × 768 px, 25 steps.

**What happened:**
- **Check before queueing:** chose `txt2img+pose+vae` and needed no licence confirmation for commercial use.
- **Generation and processing:** all 10 ran in **9.4 minutes**, about 56 s per image including processing.
- **Approval and export:** all 10 were approved and exported with one PNG preset: 10 files, no overwrites, every version `published`.

### AC-014

20 screens were opened in Polish and their text searched for raw translation keys. One problem was found and fixed (F-1 below). After the fix the screens show no raw keys. The audit log keeps the action identifier under each label on purpose, to help filtering.

## Findings

| # | Finding | Severity | Status |
|---|---|---|---|
| F-1 | **The activity feed and the audit log showed raw action names** (`generation.queued`, `svg.queued`, …) for 42 audit actions that had no label: generation, SVG, collections, export targets and presets, poses, references, styles and characters, jobs and models. The key-usage test missed them because the keys are built from data. | Medium (AC-014) | **Fixed:** all labels added in PL and EN. A new test (`test_ac014_every_audit_action_has_a_label`) collects every audit action from the backend, including the ones built at run time, and fails when one has no label in either language. |
| F-2 | **Image quality.** Style and character stay consistent across all 10 images: outfit, hair and flat style. However: <ul><li>with the base SDXL checkpoint, 3 of 10 images contain pseudo-text despite "avoid: text";</li><li>the background is not the white the style asks for;</li><li>one image (push-up) shows two figures.</li></ul> | Low (model) | **Known limitation.** Review is where such images are rejected (RULE-009). A fine-tuned checkpoint, a trained style LoRA (WP-13) or background removal and white fill in processing (WP-09) improve this. |
| F-3 | **The 5 test poses were shifted copies of the built-in ones**, so some images show a pose that does not match the exercise name (plank, mountain climber). | — (test data) | **Not a defect.** Real exercise poses come from the pose editor or from detection on a reference photo (AC-011). Pose control itself worked: images follow their pose. |
| F-4 | **An interrupted job is not retried automatically after a restart;** it waits for the user. | — | **By design (NFR-003):** the user decides, because the job may have been interrupted on purpose. |

Found earlier in WP-18 and WP-17 on the same machine and fixed there:
- **Stale images:** `start` ran old images; it now uses `compose up --build`.
- **Pipe hang:** the host agent inherited console handles.
- **Install folder:** a too-long install folder broke ComfyUI. This is now checked before any download.

## Open before release (gate G-9)

- The release procedure and versioning (G-9).
- **An SDXL LoRA training run** was not repeated here. On this GPU it takes 8–20 h; WP-01 measured it, and the app shows the estimate and warning first (RULE-016).
