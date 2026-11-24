---
title: Decision Log
type: decision-log
status: draft
created: 2026-11-21
updated: 2026-11-24
tags:
  - decisions
---

# Decision Log

User decisions recorded during Phases 0–1 (all dated 2026-11-21).

| ID | Decision |
|---|---|
| D-01 | Open-source project that anyone can run on their own machine |
| D-02 | Commercial use depends on the project; model licences are tracked per project |
| D-03 | Natural-language assistance through Claude Code + MCP; no LLM built into the app |
| D-04 | MVP example: exercise illustrations (Exerzio); one style defined by text or example images |
| D-05 | Technology chosen for quality and performance (decided by ADRs) |
| D-06 | UI in Polish and English |
| D-07 | Repository `Octanee/asset-studio` |
| D-08 | Documentation as an Obsidian vault in `docs/` |
| D-09 | Data locations configured in the app |
| D-10 | MVP platform: Windows + NVIDIA |
| D-12 | Consistent style **and** consistent characters |
| D-13 | LoRA training may be in scope |
| D-14 | Documentation in English |
| D-15 | Local environment reports stay outside the repository |
| D-17 | Distribution: Docker Compose and a native installer |
| D-18 | Licence conflicts → warning; using the model is the user's decision |
| D-19 | Native installer after the MVP |
| D-20 | Licence: Apache-2.0 |
| D-21 | No confidential data may reach the repository |
| D-22 | LoRA training in the MVP |
| D-23 | Poses from a library + editor and from detection |
| D-24 | Training on both SDXL and SD1.5 |
| D-25 | MVP also includes model management, export presets, dashboard, SVG generation |
| D-26 | Whether MCP may approve/publish is configurable per project |
| D-27 | Regeneration creates a new version of the same asset |
| D-28 | "Published" means exported to a target through a preset |
| D-29 | Single local user, no login |
| D-30 | MCP approval is off by default |
| D-31 | Reversible: rejected → review; withdraw approval; restore from archive; permanent deletion with confirmation |
| D-32 | Exerzio technical parameters set later as a project preset |
| D-33 | Re-export to the same target overwrites after explicit confirmation |
| D-34 | Background removal in the MVP |
| D-35 | Character as its own project entity |
| D-36 | Visual review by a human, optionally with Claude comments via MCP |
| D-37 | Project cloning and configuration import/export in the MVP |
| D-38 | Training data: approved assets and uploaded files |
| D-39 | Without a GPU: everything except diffusion and training works |
| D-40 | Manual backup/restore in the MVP |
| D-41 | Business scope approved, including: published-version pointer, backups without models, MoSCoW priorities, WCAG 2.2 AA, 10,000 versions per project, `processing_failed` state, archive before deleting a published version |
| D-42 | Phases run continuously, stopping at each gate; git authorisation as in [[Phase-Gates]] |
| D-43 | Documentation baseline approved (2026-11-22) |
| D-44 | One-time exception: bootstrap `main` with LICENSE and .gitignore pushed directly, because the remote was empty and a pull request needs a base branch (2026-11-22). All further changes go through pull requests |
| D-45 | UI/UX design approved as presented (2026-11-22). Open items UXQ-01–UXQ-04 stay open and are designed before their features are implemented |
| D-46 | Technical architecture (ADR-001–ADR-012) and work packages WP-00–WP-18 approved (2026-11-22) |
| D-47 | Whole library in a Docker named volume (ADR-013); Windows folders only for exports, backups, models and training exchange. Narrows D-09 (2026-11-22) |
| D-48 | Background removal on the GPU via ComfyUI (ADR-010 amended) (2026-11-22) |
| D-49 | Follow-up spike WP-01b approved, including the 2.5 GB `xinsir/controlnet-openpose-sdxl-1.0` download (2026-11-22) |
| D-50 | R-12 accepted as a known MVP limitation: floor and forward-fold poses are flagged "review and regenerate"; the full OpenPose ControlNet becomes the default pose control; pose-from-photo and character LoRA are re-tested in WP-07/WP-08 (2026-11-22) |
| D-51 | DWPose added to the backend image (ONNX Runtime, NumPy, Pillow) and its two model files installed by a checksum-verified installer; approved by the user for WP-07 (2026-11-23) |
| D-52 | WP-12 (model registry) is done before WP-08, because generation's family and licence checks need it; WP-08 then follows in two PRs: backend first, then the Generation Studio and Queue screens (2026-11-23) |
| D-53 | Generation Studio and Queue scope: the workflow is chosen from the inputs and shown in the checks (no workflow picker until workflow import); the prompt template is the style and character text added to the prompt; Queue has cancel, retry and resume but not pause or reorder, which no FR requires; version tiles show the original file until WP-09 makes thumbnails (2026-11-23) |
| D-54 | Processing and validation (WP-09): processing runs on its own after generation as jobs (`remove_background` on the GPU lane when the project asks for it, then `process` on the CPU lane); size, format and background come from `output`, the steps from a new `processing` section and the limits from `validation`, both with defaults so existing configurations stay valid; the processed file, the cut-out, the thumbnail and the preview are new files next to the untouched original, each written once (RULE-003); validation results are informative (`passed`/`failed`/`skipped`), never block review (RULE-009) and are kept per run; BiRefNet from `Comfy-Org/BiRefNet` (MIT) is a catalogue model of the new kind `segmentation`, installed through the approved download flow (2026-11-23) |
| D-55 | Library and review scope (WP-10): tags are lower case with words joined by `-`, at most 20 per asset, suggested from the project's tags (FR-049); a favourite is a mark on the asset (single user, FR-057); a collection groups a project's assets and deleting it never changes them (FR-056); duplicates are other versions of the project with the same file (SHA-256) or a difference hash of the processed image at most 6 of 64 bits apart, shown as information only (FR-059); the review queue is oldest first; comments are append-only, from the user or Claude, and Claude may always comment (FR-064, RULE-005); Compare has side by side, swipe and overlay with one zoom and pan; the pose overlay is deferred because version metadata does not keep the keypoints; publishing from the library arrives with WP-11 (2026-11-23) |
| D-56 | Publishing (WP-11): one export root, a Windows folder mounted at `/exports` (`ASSET_STUDIO_EXPORTS_HOST_DIR`); targets are subfolders of a root and the API shows root names, not host paths; a preset renders the processed file (or the original) to each of its sizes, so the library files are never changed; placeholder values are reduced to safe characters so no pattern can leave the target; a plan is used once and is valid for one hour; existing files are checked again when publishing and once more by the job, and a file that appears in between is never overwritten; for a collection or the whole project each asset contributes its newest approved or published version; MCP publishing needs `mcp_can_decide`, never overwrites and never publishes again (T-10); the optional metadata sidecar holds the asset, version, prompt, seed and model ids, never paths; "export only" without publishing is deferred (2026-11-23) |
| D-57 | MCP server (WP-15): a stateless Streamable HTTP server in the backend package `asset_studio_mcp`, run as its own compose service with no database settings, volumes or token of its own; it forwards the caller's MCP token to the API, so every rule stays in the API; tool answers that are lists are wrapped as `{items, count}`; besides the designed tools it offers `generate_check`, `review_queue`, `asset_image` (so Claude can look at a version before commenting), `style_list`, `character_list` and `publish_options`; every change is audited by the API with actor `mcp`, while reads are not written to the audit log (MCP-Architecture said every tool call); idempotency keys are stored per actor for 24 hours (2026-11-23) |
| D-58 | Dashboard, settings, status and backup (WP-16): data locations, the engine address and tokens come from `.env` and are shown read-only (folder names and counts, never host paths), so a change needs a restart; the MCP token is never shown and is changed in `.env` (MCP-Architecture had "shown once and rotatable"); the app stores only what it changes itself in `setting` (`queue_paused`); pausing the queue lets running jobs finish and starts nothing new except backup and restore; backups are written with `COPY` in one snapshot instead of `pg_dump` (no PostgreSQL client in the image) and always include every library file, derived ones too; restore loads a scratch schema migrated to the backup's revision, then to the current one, and copies the rows into the live tables in one transaction; jobs that were queued or running come back cancelled; the dashboard reminds about a backup after 7 days; the Projects screen (FR-001–FR-006) follows as the second part of WP-16 (2026-11-24) |
| D-59 | Projects screens (WP-16 part 2): Projects lists every project with counts and the drafts waiting for the user; New project edits a configuration with a live schema check (`projects:validate`), and a draft from Claude opens in the same editor, where only the user creates the project or discards the draft (RULE-010); the app does not call Claude itself: to revise a draft the user asks Claude in Claude Code; Project settings keeps the form for the main fields and the whole configuration as JSON, saves every change as a new configuration version, asks before a breaking change (FR-007), compares a version with the current one and loads an old version into the editor, so restoring also creates a new version and history is never rewritten; Claude's permission to decide is a checkbox, off by default (RULE-005) (2026-11-24) |
| D-60 | LoRA training (WP-13 part 1): datasets take approved or published versions of the project and uploads (5–200 images, each image once) with captions; the trigger word starts every caption and names kohya's class folder; presets for small GPUs from the prototype (SD1.5: AdamW8bit, 512 px, UNet and text encoder without gradient checkpointing, ~0.8 s/step measured in the app: 400 steps in about 6 min (the prototype's 0.6 s was a 40-step test; gradient checkpointing nearly doubled the time); SDXL: UNet only, gradient checkpointing, Adafactor, bf16, cached latents and text encoder outputs, fp16-fix VAE, 768 px, ~30 s/step); steps default to 100 per image (SD1.5) or 60 (SDXL), 300–3000; the estimate is the measured 6 GB speed, and SDXL on less than 12 GB of VRAM needs it acknowledged (RULE-016); one queued run per project; the `train` job hands the GPU over by stopping ComfyUI and starting it again afterwards, and is exempt from the engine gate; the trained LoRA gets the base model's licence and is never written over an existing file; only kohya's exit code leaves the host agent, the log stays on the computer; linking LoRAs to styles and characters and using them in generation follow in part 2 (2026-11-24) |
| D-61 | LoRAs in generation (WP-13 part 2): a style or character links at most two LoRAs with a strength (user or Claude: configuration, not a decision); a generation uses the LoRAs it names plus the linked ones (character first, then style; a named LoRA sets its own strength), at most two because the templates chain two `LoraLoader` nodes; a LoRA must match the checkpoint's family (RULE-015); a trained LoRA's trigger word, taken from its training run, starts the prompt; the version's metadata records each LoRA (RULE-011); the Generation Studio shows the LoRAs and the final prompt from the check, and LoRAs are picked through styles and characters rather than per request in the UI (the API accepts both) (2026-11-24) |
| D-62 | SVG generation (WP-14): the UXQ-01 SVG Studio design was approved by the user (2026-11-24) and added to the navigation after Generation Studio. Templates are versioned code with typed parameters (glyph, colour, number), so the same template version and parameters give the same file, and the preview is that file; a version records the template, its parameters and their hash (RULE-011). Every stored SVG passes an allow-list sanitiser (shapes and presentation attributes only; scripts, `style`, events, links, images, text, foreign namespaces and external `url()` are dropped; a DOCTYPE or entity is refused) that also writes one compact canonical form, which is the optimisation. An SVG version stays a vector: processing keeps the cleaned SVG and renders it with resvg (`resvg-py`, MIT, about 1.3 MB) for the thumbnail, preview, duplicate check and the pixel validation rules; export renders it at each preset size or copies it with the new `svg` preset format, which skips raster versions (`NOT_VECTOR`). With a style, colours must be in its palette, plus white and black. SVG versions cannot be training images or image-to-image inputs (2026-11-24) |
| D-63 | Setup and start scripts (WP-17): one `asset-studio.cmd` → `scripts/asset-studio.ps1` for the stock Windows PowerShell 5.1 (ASCII files, no extra modules; tested with plain asserts in a Windows CI job). Native components are pinned in `scripts/native-components.json`: ComfyUI portable v0.46.0 and `7zr` 26.04 by size and SHA-256 (downloaded with `curl.exe`, resumable; a mismatch deletes the file), ComfyUI_IPAdapter_plus and kohya sd-scripts by commit, torch 2.6.0 from the CUDA 12.4 index. Each install lists every download with host, size and licence and needs a typed `y`; there is no flag to skip the question. Setup generates only empty or placeholder secrets. With Windows long paths off, an install folder that would push files past 260 characters is refused before any download (ComfyUI nests 185 characters deep). The host agent starts through `cmd.exe` so it inherits no console handles. `start` runs `compose up --build`, so an update never runs old images (2026-11-24) |

IDs D-11 (licence delegated → D-20) and D-16 (ambiguous → D-18) were superseded and are kept for history.
