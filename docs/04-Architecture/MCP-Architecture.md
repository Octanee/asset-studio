---
title: MCP Architecture
type: architecture
status: approved
created: 2026-11-22
updated: 2026-11-22
tags:
  - architecture
  - mcp
---

# MCP Architecture

- **Server:** Python with the official MCP SDK. Transport is **Streamable HTTP** at `127.0.0.1:<port>/mcp`, and Claude Code connects to it as an HTTP MCP server.
- **Auth:** a per-install **MCP token**, shown once in Settings › MCP connection and rotatable. The MCP server forwards it to the API, which maps it to actor `mcp`.
- **No bypass:** the MCP server has **no database or file access**; it only calls the REST API (brief §10).

## Tools

| Tool | API | Permission |
|---|---|---|
| `project_list`, `project_get`, `project_validate` | GET / validate | read |
| `project_draft_create`, `project_draft_update` | `POST /projects/drafts` | draft only; **the user confirms in UI** (RULE-010) |
| `style_create`, `style_get`, `style_update` | styles | draft changes recorded as a new style version |
| `reference_upload` | references | validated like any upload; base64 limited to 20 MB |
| `pose_list`, `pose_detect` | poses | job |
| `workflow_list`, `model_list`, `engine_status` | GET | read |
| `generate_image`, `generate_batch` | `POST /generations` | Idempotency-Key required |
| `generation_status`, `generation_cancel` | jobs | own and user jobs |
| `asset_list`, `asset_get`, `asset_validate` | assets | read |
| `asset_comment` | comments | always allowed |
| `asset_approve`, `asset_reject` | transitions | only if `mcp_can_decide` (RULE-005) |
| `asset_publish` | publications | only if `mcp_can_decide`; **never overwrites** — a plan with overwrites is refused (RULE-004) |

Not exposed:
- permanent delete;
- enabling `mcp_can_decide`;
- model downloads;
- licence acknowledgements;
- settings, backup and restore;
- any filesystem path or shell.

Long operations return a job id; the client polls `generation_status`. Every tool call is audited with actor `mcp`.
