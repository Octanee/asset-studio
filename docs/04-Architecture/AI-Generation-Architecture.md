---
title: AI Generation Architecture
type: architecture
status: approved
created: 2026-11-22
updated: 2026-11-24
tags:
  - architecture
  - ai
---

# AI Generation Architecture

## Provider adapters

```mermaid
classDiagram
  class GenerationProvider {
    <<interface>>
    +capabilities() Capabilities
    +health() Health
    +submit(request) ProviderJobRef
    +progress(ref) Progress
    +cancel(ref)
    +collect(ref) list~OutputFile~
    +free_vram()
  }
  class TrainingProvider {
    <<interface>>
    +estimate(run, hardware) Estimate
    +start(run) ProviderJobRef
    +progress(ref) Progress
    +cancel(ref)
  }
  GenerationProvider <|.. ComfyUIProvider
  GenerationProvider <|.. FakeProvider
  GenerationProvider <|.. SvgTemplateProvider
  TrainingProvider <|.. KohyaProvider
  TrainingProvider <|.. FakeTrainingProvider
```

- **ComfyUIProvider** (worker → ComfyUI HTTP `/prompt`, `/history`, `/view`, `/free`, plus WebSocket `/ws` for step progress).
  - It translates a domain `GenerationRequest` into ComfyUI API-format JSON using a **workflow version**: a template with declared inputs, like the prototype's `make_workflows.py`.
  - The domain never sees ComfyUI node ids.
- **SvgTemplateProvider:** deterministic SVG from versioned templates. It runs in-process with no GPU, is sanitized, and is rasterized with `resvg`.
- **FakeProvider:** returns generated test images with configurable delays and failures, for CI and UI development.
- **KohyaProvider:** runs through the host agent (see below), using presets for 6 GB taken from the prototype:
  - SDXL: UNet-only, Adafactor fused, bf16, gradient checkpointing, cached latents/TE, 768 px;
  - SD1.5: AdamW8bit, 512 px.

## GPU lane

The worker owns **one GPU lane**, so a single job uses the GPU at a time (RULE-012).

- **Before training:** call `free_vram()` on ComfyUI, then ask the host agent to stop it. Training starts only once VRAM is under the threshold.
- **After training:** restart ComfyUI, then resume generation jobs.
- **Engine unavailable:** GPU jobs stay `queued` with a reason (RULE-013); CPU jobs continue.

## Host agent

The host agent is a small native Windows service in Python, listening on 127.0.0.1 with a per-install token. Its API is **fixed and narrow**:
- `GET /health`, `GET /gpu` (nvidia-smi query);
- `POST /engine:start|stop|restart` (ComfyUI with pinned args);
- `POST /training-runs` (a validated run spec only; the agent builds the kohya command from it; no shell, no arbitrary args);
- `GET /training-runs/{id}` (progress parsed from logs), `POST /training-runs/{id}:cancel`.

It sets `PYTHONUTF8=1` (prototype S-3) and keeps kohya in its own Python 3.11 venv.

## Pose detection and background removal

| Function | Choice | Licence | Where |
|---|---|---|---|
| Pose detection | DWPose (ONNX: YOLOX detector + DW-LL pose) | Apache-2.0, code via mmpose (to confirm upstream) | worker, ONNX Runtime CPU |
| Background removal | BiRefNet | MIT | ComfyUI workflow on the GPU (D-48) |

- **Pose detection** runs on CPU: 2–4 s per image in WP-01, so it is usable while ComfyUI is stopped.
- **Background removal** runs on the GPU. On CPU it took 22–141 s and ~19 GB RAM in WP-01, so it waits for the engine like diffusion (D-48).
- **Implemented (WP-09):** the `remove_background` workflow template (v1) uses ComfyUI's native nodes (`LoadBackgroundRemovalModel`, `RemoveBackground`, `MaskToImage`) and returns the foreground mask; `modules/processing` builds the cut-out from the untouched original and the mask, then `process` fills the background, resizes, converts and optimises, and `modules/quality` validates the result (D-54). The model is the catalogue entry `birefnet-comfy` (kind `segmentation`).

## Reproducibility metadata (RULE-011)

Each version stores:
- `model {id, sha256}`, `lora [{id, sha256, weight}]`;
- `workflow {id, version}`, `engine {name, version}`;
- `prompt`, `negative`, `seed`, `steps`, `cfg`, `sampler`, `scheduler`, `size`;
- `pose {id, keypoints hash, strength}`, `references [{id, sha256, weight}]`;
- `hardware {gpu, vram}`.

## Models and downloads

The registry is seeded from a **versioned catalogue file** in the repo (name, source URL, sha256, size, licence, family, VRAM). Downloads:
- need explicit approval (RULE-008);
- go to a temp file;
- are resumable with HTTP ranges and lock against duplicates;
- are verified by SHA-256, then moved into the model folder (prototype S-1).

### Implementation notes (WP-08, generation backend)

- **Workflows:** `modules/workflows/builtin.py` builds 16 versioned templates from the graph the WP-01 spike ran: text-to-image or image-to-image, plus optional OpenPose ControlNet, IP-Adapter reference and a separate VAE (id e.g. `txt2img+pose+reference+vae`, version 1). The request chooses features from its inputs; there is no workflow choice in the UI yet.
- **Requests:** `modules/generation/service.py` resolves the style, character, pose, reference or init image and the models. Add-on models are picked from installed models of the checkpoint's family (the xinsir OpenPose ControlNet first, D-50; the SDXL fp16 VAE). It composes the prompt from the request, the character (description, traits) and the style (description, rendering, lighting, background, project attributes); the negative prompt joins the request with both avoid lists.
- **Checks before queueing:** model compatibility and install state (FR-084, RULE-015), missing add-ons, an empty prompt, then the licence gate (RULE-007). The engine being down is not a blocker: jobs wait (RULE-013).
- **Jobs:** one `generate` job on the GPU lane per variant (seed + n) and per batch item (each a new asset, FR-034). Params are frozen: resolved files, prompts, pose keypoints and reference keys, plus the request for regeneration.
- **The job:** renders the pose as an OpenPose image fitted to the output size, uploads images through `/upload/image`, runs the engine with step progress from `/ws` (`progress` messages; polling stays the fallback), and stores each output as a new `generated` version with metadata: workflow, engine, models with hashes, prompts, seed and sampling parameters, size, style and character versions, pose, references, hardware (RULE-011). References are linked to the job and the version (FR-026).
- **Regeneration (FR-052, AC-002):** replays the stored request for the same asset with changes; the earlier version is untouched.
- **Verified on the GPU:** SDXL + OpenPose ControlNet + IP-Adapter at 1024², 25 steps, with step progress, then regenerated with another seed.
- **LoRAs (WP-13):** every template has variants with one or two `LoraLoader` nodes after the checkpoint (`+lora`, `+lora2`); the prompts, the sampler and IP-Adapter take the last LoRA's model and text encoder. A generation uses the LoRAs it names and those linked to its style and character (a named one sets its own strength), at most two, of the checkpoint's family (RULE-015). A trained LoRA's trigger word starts the prompt. The version's metadata lists each LoRA with file, hash, strength and trigger word (RULE-011).
- **Not yet:** one reference image per generation. Post-processing and validation start on their own after each generated version (WP-09).

### Implementation notes (WP-08, screens)

- **Generation Studio** (`frontend/src/pages/GenerationStudio.tsx`): single asset (new, or a new version of an existing one) or a batch from a list (one line per asset; text after `|` is added to its prompt). Style, character, pose with strength, reference with weight, start image for image-to-image, prompt, negative prompt, variants 1/2/4/8, and the model and sampling parameters. The request is checked with `POST /generations:check` 0.4 s after the last change: problems, licences to confirm (with a link to Models), the engine state, the workflow, models and the final prompt. Queueing is disabled with a reason until the check is ready (DD-008); a stopped engine is a note, not a blocker (RULE-013). After queueing, the screen follows its jobs (step progress, reason for waiting, cancel) and shows the asset's versions, newest first, each with "new version (new seed)" (FR-052).
- **Queue** (`frontend/src/pages/Queue.tsx`): all jobs or the current project's, filtered by state; workflow and seed for generation jobs, step progress, the reason for waiting or the error, run time; cancel, retry (failed) and resume (interrupted), and retry of all failed. The GPU panel shows the device and VRAM use from the engine status and why GPU jobs wait (RULE-012, RULE-013). Live job events refresh both screens; polling only covers a lost event stream.
- **Scope (D-53):** no workflow picker, queue pause or reorder yet; tiles use the original file until WP-09 creates thumbnails.

### Implementation notes (WP-12)

- **Catalogue:** `backend/src/asset_studio/modules/models/catalogue.json` (families, licences, models with HTTPS source, SHA-256 and size). Each entry was checked against the source's LFS metadata when added. It is synced into the database when the registry is read.
- **Model folder:** the host folder `ASSET_STUDIO_MODELS_HOST_DIR` in ComfyUI's layout (`checkpoints`, `loras`, `controlnet`, `ipadapter`, `clip_vision`, `vae`) is mounted read-only into the API (scan) and read-write into the worker (downloads). DWPose files stay in `<data>/models/pose`.
- **Scan (FR-081):** a file with the catalogue's name is that model; any other model file becomes a `local` model with an unknown licence and family (the user can set the family). A size different from the catalogue marks the file as mismatched; a changed size makes a verified file unverified again.
- **Downloads (FR-082, RULE-008, NFR-007):** the user confirms file, source and size, which must equal the catalogue entry. A `download` job on the CPU lane writes `<file>.part`, resumes with `Range` (a server without ranges restarts it), refuses non-HTTPS redirects, checks the SHA-256 and only then renames the file. A wrong file is deleted; an interrupted one stays for the next attempt. One download per model at a time.
- **Checks:** `verify_model` jobs hash an installed file. Compatibility (FR-084, RULE-015): one checkpoint, add-ons of the same family, IP-Adapter needs CLIP vision, files installed and not mismatched.
- **Licences (RULE-007, FR-083):** a commercial project conflicts with any licence whose commercial use is not `allowed` (`unknown` included). The user confirms per project and model, with an optional note; it is audited and stays valid while the licence and the intended use are unchanged. `licence_gate` is the check WP-08 runs before queueing.

## Implementation notes (WP-05)

- **Code:** `backend/src/asset_studio/modules/providers/`:
  - `base.py`: the `GenerationProvider` protocol and its value types;
  - `workflows.py`: workflow templates whose declared inputs target `(node, field)` pairs, so the domain never sees node ids; inputs are type- and range-checked and fail with `WORKFLOW_INPUT_INVALID`;
  - `fake.py`: deterministic PNGs per seed, configurable steps and failures, no imaging library;
  - `comfyui.py`: `/system_stats`, `/prompt`, `/history`, `/queue`, `/interrupt`, `/view` and `/free`;
  - `engine.py`: `EngineMonitor` (health cached for 5 s) and `run_generation` (submit, follow, collect; cancels the engine job when the user cancels or the worker stops).
- **GPU lane:** the worker registers `EngineMonitor.gate` for the `gpu` lane. While the engine is down, GPU jobs stay `queued` with `wait_reason = ENGINE_UNAVAILABLE` (RULE-013) and CPU jobs keep running. The gate takes effect once GPU job handlers exist (generation in WP-08).
- **Step progress:** the adapter reports queue position and completion. Per-step progress over ComfyUI's `/ws` socket was added in WP-08.
- **Problem codes:** `ENGINE_UNAVAILABLE` (503), `ENGINE_REJECTED` (ComfyUI refused the graph; lists the node ids), `ENGINE_ERROR`, `GENERATION_FAILED` (with the engine's message).
- **Host agent:**
  - `GET /gpu` runs `nvidia-smi` with fixed arguments;
  - `GET /engine` and `POST /engine:start|stop|restart` supervise the portable build: `python_embeded/python.exe -s ComfyUI/main.py --windows-standalone-build --listen 127.0.0.1 --port <port> --disable-auto-launch`, with `PYTHONUTF8=1`, output to `comfyui.log`, no shell and no request-supplied arguments;
  - stop terminates the process and kills it after 20 s; the agent stops the engine when it shuts down;
  - errors: `ENGINE_NOT_CONFIGURED`, `ENGINE_NOT_INSTALLED`.
- **Engine API:** `GET /api/v1/system/engine` and `POST /api/v1/system/engine/{start|stop|restart}` (user only, audited as `engine.<action>`). The top bar and the System status screen show this and explain disabled controls (DD-008).
- **Training (WP-13, implemented):**
  - The `train` job writes the run's images and captions to the training exchange folder (`ASSET_STUDIO_TRAINING_HOST_DIR`, the worker's `/training`) in kohya's layout: a class folder `1_<trigger>`, and each caption starts with the trigger word.
  - It asks ComfyUI to free its VRAM, stops it through the host agent, starts kohya through `POST /training-runs`, polls the step progress and starts ComfyUI again at the end.
  - `train` is exempt from the engine gate: it does not need ComfyUI.
  - Cancelling the job cancels kohya.
  - The LoRA is copied into the shared model folder (`loras/`), never over an existing file, and registered with its family and the base model's licence.
  - With the fake engine a fake trainer stands in.
- **Host agent training:**
  - Settings: `ASSET_STUDIO_AGENT_KOHYA_DIR` (sd-scripts with `.venv`), `_MODELS_DIR`, `_TRAINING_DIR`.
  - A run spec carries only the run id, family, base model and VAE file names, output name, resolution, steps, rank, alpha, learning rate and seed. The agent builds the command from its presets.
  - Only the exit code leaves the agent; the log stays in the run's folder.
- **Not yet:**
  - installing the pinned ComfyUI build and kohya (WP-17);
  - SVG templates (WP-14);
  - (LoRAs in generation: done in WP-13 part 2, see above.)
