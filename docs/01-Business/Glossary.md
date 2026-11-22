---
title: Glossary
type: glossary
status: approved
created: 2026-11-21
updated: 2026-11-21
tags:
  - glossary
---

# Glossary

| Term | Definition |
|---|---|
| **Platform** | Reusable capabilities and business logic shared by all projects. |
| **Project** | An independent configuration (styles, characters, presets, rules) that uses the platform. |
| **Project configuration** | The versioned, schema-validated description of a project; it can be cloned, exported and imported. |
| **Style** | A reusable description of visual identity: text attributes and/or reference images. |
| **Character** | A recurring subject in a project: name, description, references, optional LoRA. |
| **Pose** | A body skeleton (keypoints) used to control the figure's position; it comes from the library, the editor or detection. |
| **Reference** | An uploaded image with a role (style, character, pose, composition, …). |
| **Asset** | A logical item of a project (e.g. "squat illustration") with a category and versions. |
| **Asset version** | One concrete file produced by a generation or import. It carries the lifecycle status. |
| **Currently published version** | The pointer on an asset to the version last exported to a given target. |
| **Generation job** | A persistent unit of work in the queue (generation, training, processing). |
| **Workflow** | A versioned definition of a generation pipeline run by an engine. |
| **Engine / provider** | A component that executes workflows (initially ComfyUI), behind an adapter. |
| **LoRA** | A small trained add-on to a base model that captures a style or character. |
| **Model family** | A base-model lineage (SDXL, SD1.5); a LoRA works only within its family. |
| **Technical validation** | Automatic checks of a file (dimensions, format, size, transparency, naming). |
| **Visual review** | Assessment of style, correctness and quality by a human, with optional comments from Claude. |
| **Export preset** | Rules for format, size, naming and folder structure used when exporting. |
| **Export target** | A folder that receives exported files (e.g. another app's repository). |
| **Publish** | Exporting an approved version to a target through a preset. |
| **Audit entry** | An immutable record of who (`user` / `mcp` / `system`) did what, when, and why. |
| **MCP** | Model Context Protocol: the controlled tool interface Claude Code uses to work with the app. |
| **Reference machine** | The baseline hardware for performance goals: an NVIDIA laptop GPU with 6 GB VRAM and 32 GB RAM. |
