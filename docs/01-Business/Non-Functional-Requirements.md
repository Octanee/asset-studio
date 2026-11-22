---
title: Non-Functional Requirements
type: non-functional-requirements
status: approved
created: 2026-11-21
updated: 2026-11-21
tags:
  - requirements
  - non-functional
---

# Non-Functional Requirements

| ID | Category | Requirement | Source |
|---|---|---|---|
| NFR-001 | Platform | Runs on Windows 11 with an NVIDIA GPU with ≥ 6 GB VRAM (reference machine: 6 GB VRAM laptop GPU, 32 GB RAM). The architecture must not rule out other platforms. | D-10 |
| NFR-002 | Performance | The full pipeline (SDXL + pose + reference conditioning, 1024²) completes in about 1–2.5 min per image on the reference machine; the UI shows progress and an estimate. | prototype |
| NFR-003 | Reliability | Job queue and history survive application and engine restarts; interrupted jobs are marked and can be retried. | brief §5.3 |
| NFR-004 | Localisation | UI in Polish and English; documentation in English. | D-06, D-14 |
| NFR-005 | Security | All services listen on loopback only by default; LAN access is out of scope. | D-29, brief §9 |
| NFR-006 | Offline | Fully usable offline except for model downloads the user approves. | brief §2.2 |
| NFR-007 | Integrity | Model downloads are resumable and verified by SHA-256. | prototype S-1 |
| NFR-008 | Maintainability | The generation engine version is pinned and tested; engine-specific details stay behind an adapter. | prototype S-6, brief §5.1 |
| NFR-009 | Accessibility | Target WCAG 2.2 AA for the web UI. | brief §8.1, D-41 |
| NFR-010 | Scalability | Smooth browsing of 10,000 versions per project. | brief §8.1, D-41 |
| NFR-011 | Security | Uploaded files, filenames, metadata, prompts and workflow definitions are untrusted: validated MIME/type and size limits, path-traversal protection, SVG sanitization. | brief §9 |
| NFR-012 | Privacy | Logs contain no secrets or personal data; nothing leaves the machine except approved downloads. | brief §9 |
| NFR-013 | Distribution | The MVP ships as Docker Compose, plus ComfyUI running natively on Windows; a native installer comes after the MVP. | D-17, D-19 |
| NFR-014 | Robustness | Subprocesses run with UTF-8 I/O (avoids locale encoding errors on Windows). | prototype S-3 |
| NFR-015 | Testability | CI runs without a GPU, using mocked generation providers; GPU tests are isolated. | brief §14.1 |
| NFR-016 | Licensing | Application code is Apache-2.0; GPL components (e.g. ComfyUI) run as separate processes and are not linked. | D-20 |
| NFR-017 | Data safety | Backups can be verified for integrity before restore. | brief §9 |
