---
title: Decision Log
type: decision-log
status: draft
created: 2026-11-21
updated: 2026-11-23
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

IDs D-11 (licence delegated → D-20) and D-16 (ambiguous → D-18) were superseded and are kept for history.
