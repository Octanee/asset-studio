---
title: WP-01 Spike Report
type: spike-report
status: in-review
created: 2026-11-22
updated: 2026-11-22
tags:
  - spike
  - wp-01
  - risks
---

# WP-01 — Verification Spikes

The spikes ran on the reference machine: a 6 GB VRAM NVIDIA laptop GPU, 8-core CPU and 32 GB RAM, with Docker Desktop on WSL2. The scripts are in `spikes/wp-01/`. Generated images and model files stay outside the repository.

| Risk / ADR | Question | Result | Proposal |
|---|---|---|---|
| R-21 / ADR-005, ADR-007 | Is a bind-mounted NTFS data folder fast enough for the library? | ❌ **No, for many small files** | ADR-013 (below) |
| R-19 / ADR-009 | DWPose licence, CPU speed, quality | ✅ licence verified, fast enough on CPU | keep ADR-009 |
| R-20 / ADR-010 | BiRefNet licence, CPU speed, quality | ✅ licence and quality; ❌ CPU speed and memory | change ADR-010 (below) |
| R-12 | Same character across 10 different poses | ⚠️ identity ✅; pose fidelity only for upright poses | follow-up spike WP-01b (below) |

## R-21 — storage speed (`bench_storage.py`)

The benchmark ran in the backend container, twice for each storage type:
- write 2,000 × 40 kB files using temp file + rename;
- write 20 × 8 MB files;
- read everything back;
- delete.

| Operation | Bind mount (NTFS via WSL2) | Docker named volume (ext4) |
|---|---|---|
| Write 2,000 small files | 15.9–22.1 s (91–126 files/s) | 1.2–1.7 s (1,199–1,609 files/s) |
| Read 2,000 small files (library scroll) | **14.3–23.7 s** | **0.10–0.12 s** |
| Write 20 × 8 MB | 0.77–1.08 s (148–208 MB/s) | 0.08–0.10 s |
| Read 20 × 8 MB | 0.70–0.97 s | 0.03–0.04 s |
| Delete all | 9.3–11.2 s | 0.15 s |

**Conclusion:**
- Large files on the bind mount are fine. Generation writes about 1 image per minute.
- Reading many small files is ~150× slower, which breaks NFR-010 (smooth browsing of 10,000 versions).

### Proposed ADR-013: derived files in a Docker volume

- **Originals and references** stay in the user's data folder (bind mount), as D-09 requires: they are user-visible, backed up, and written rarely.
- **Thumbnails and previews**, which are regenerable, live in a named volume `asset-cache` that the API serves from.
- A cache miss regenerates the file from the original.
- Backup excludes the cache (Storage-and-Backup already treats derived files as optional).

## R-19 — DWPose (`onnx_cpu.py`)

**Licences, verified in the upstream repositories:**
- `IDEA-Research/DWPose`: Apache-2.0;
- `open-mmlab/mmpose`: Apache-2.0;
- `Megvii-BaseDetection/YOLOX`: Apache-2.0;
- model card `yzd-v/DWPose`: Apache-2.0.

The training-data terms behind the checkpoints are not stated by these sources; they are recorded in the model catalogue as "see upstream".

**CPU in the worker container (ONNX Runtime 1.20.1):**
- person detection (YOLOX-L, 640²): **1.5–3.2 s**;
- whole-body pose (DW-LL 384×288): **0.4–1.3 s**;
- models load once in about 40–60 s, so the worker should keep them loaded.

**Quality on generated illustrations:**
- 3 of 4 images were detected, with mean keypoint confidence 0.60–0.68, and the skeletons followed the figure.
- 1 standing figure was missed at detector threshold 0.3. The threshold needs tuning in WP-07, plus a manual fallback (draw the box or edit the pose).

**Decision:** keep ADR-009 (DWPose on CPU).

## R-20 — BiRefNet (`onnx_cpu.py`)

**Licences, verified upstream:** `ZhengPeng7/BiRefNet` MIT; model cards `onnx-community/BiRefNet-ONNX` and `BiRefNet_lite-ONNX` MIT.

**Quality:** excellent cut-outs on flat-vector illustrations; hair and laces were kept.

**CPU speed:**
- full model: **41–141 s per 1024² image**;
- lite model: **22–74 s**;
- the container used **~19 GB RAM**.

This is far too slow and memory-hungry for a processing step on the reference machine.

### Proposed change to ADR-010

- Run BiRefNet as a **ComfyUI workflow on the GPU** (supported natively by ComfyUI) in the GPU lane.
- When the engine is stopped, *background removal* steps wait in the queue with a clear status. All other processing, validation, review and export keep working.
- This narrows how RULE-013 is applied: background removal joins diffusion and training as GPU-dependent work. **It needs the user's approval.**

## R-12 — consistency across poses (`r12_poses.py`)

**Setup:**
- 10 exercise skeletons (COCO-18) built from joint angles;
- SDXL base, OpenPose Control-LoRA (rank 256) at strength 0.9, and IP-Adapter Plus with the same character reference at weight 0.6;
- seeds 3000–3009, 1024², 25 steps;
- about 68–138 s per image, 16.8 min in total.

**Results:**

| Aspect | Result |
|---|---|
| Character identity (hair, outfit, colours, style) | ✅ consistent in **10/10** |
| Upright poses (standing, squat, lunge, high knees, jumping jacks) | ✅ **5/5** follow the skeleton |
| Floor and hinge poses (plank, push-up, glute bridge, deadlift, toe touch) | ❌ **0/5** at default settings |
| Same 5 poses with reference weight 0.4 (ending at 60% of steps) and pose strength 1.0 | ⚠️ **2/5** acceptable (plank, push-up; the push-up had an extra-leg artifact); the bridge and toe touch were still wrong; the deadlift produced two figures |
| Background | ❌ grey instead of the requested white in 15/15. The prompt alone is not enough; post-processing (background removal or a flat fill) is needed |

**Conclusion:**
- Identity consistency through reference conditioning works.
- Pose fidelity for non-upright exercises is **not yet reliable** with the Control-LoRA on 6 GB.
- R-12 stays **open**.

### Proposed follow-up spike WP-01b (before WP-08)

1. Full **SDXL OpenPose ControlNet** (`xinsir/controlnet-openpose-sdxl-1.0`, Apache-2.0, 2.5 GB download) instead of the Control-LoRA.
2. Skeletons taken from **detected real poses** (DWPose on reference photos the user supplies) instead of synthetic angles.
3. Reference scheduling, i.e. applying the reference only to part of the sampling steps, plus an optional pose-specific reference.
4. Success criterion: ≥ 8/10 poses correct, with identity kept.

If WP-01b fails, the fallback options are:
- a character LoRA (D-22);
- depth or line-art control from a posed 3D mannequin;
- documenting that floor poses need manual review and regeneration.

## Effect on the plan

- WP-02 to WP-06 can start; they do not depend on these results.
- ADR-013 and the ADR-010 change must be approved before WP-03 (storage) and WP-09 (processing).
- WP-01b must run before WP-08 (Generation Studio).
