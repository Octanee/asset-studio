---
title: MCP Architecture
type: architecture
status: approved
created: 2026-11-22
updated: 2026-11-23
tags:
  - architecture
  - mcp
---

# MCP Architecture

- **Server:** Python with the official MCP SDK (`backend/src/asset_studio_mcp`, WP-15). Transport is **Streamable HTTP** at `127.0.0.1:<port>/mcp` (stateless, JSON answers), and Claude Code connects to it as an HTTP MCP server. It runs as the compose service `mcp` from the backend image, published only on loopback (default port 8411), with DNS-rebinding protection (loopback `Host` and `Origin` only).
- **Auth:** a per-install **MCP token**, shown once in Settings › MCP connection and rotatable. The MCP server forwards it to the API, which maps it to actor `mcp`.
- **No bypass:** the MCP server has **no database or file access**; it only calls the REST API (brief §10). The `mcp` service has no volumes and no database settings, and an import contract forbids the package from importing the backend, SQLAlchemy or psycopg.
- **Errors:** an API refusal becomes a tool error carrying the problem code and detail (e.g. `MCP_NOT_ALLOWED (403)`), so Claude can tell the user why (FR-121).

## Tools

| Tool | API | Permission |
|---|---|---|
| `project_list`, `project_get`, `project_validate` | GET / `POST /projects:validate` | read |
| `project_draft_create`, `project_draft_update` | `POST /projects/drafts`, `PUT /projects/drafts/{id}` | draft only; **the user confirms in UI** (RULE-010) |
| `style_list`, `style_create`, `style_get`, `style_update`, `character_list` | styles, characters | every change is a new style version |
| `reference_upload` | references | validated like any upload; base64 limited to 20 MB |
| `pose_list`, `pose_detect` | poses | job |
| `workflow_list`, `model_list`, `engine_status` | GET | read |
| `generate_check` | `POST /generations:check` | read |
| `generate_image`, `generate_batch` | `POST /generations` | Idempotency-Key required (the tool's `request_id`) |
| `generation_status`, `generation_cancel` | jobs | own and user jobs |
| `asset_list`, `asset_get`, `asset_validate`, `review_queue` | assets, versions, validation | read |
| `asset_image` | `GET /versions/{id}/file` | read; the preview (or the original before processing) as an image Claude can look at |
| `asset_comment` | comments | always allowed |
| `asset_approve`, `asset_reject` | transitions | only if `mcp_can_decide` (RULE-005) |
| `publish_options` | presets, targets | read |
| `asset_publish` | `POST /publications:plan`, `POST /publications` | only if `mcp_can_decide`; **never overwrites** — a plan with overwrites is refused (RULE-004); never publishes again (T-10) |

Not exposed:
- permanent delete;
- enabling `mcp_can_decide`;
- model downloads;
- licence acknowledgements;
- settings, backup and restore;
- any filesystem path or shell.

Long operations return a job id; the client polls `generation_status`. Every change a tool makes is audited by the API with actor `mcp`; reads are not written to the audit log (D-57).

## Connecting Claude Code

Set `ASSET_STUDIO_MCP_TOKEN` in `.env` (a long random value) and start the stack. Then add the server once:

```
claude mcp add --transport http asset-studio http://127.0.0.1:8411/mcp --header "Authorization: Bearer <ASSET_STUDIO_MCP_TOKEN>"
```

Requests without the bearer token are refused with 401; a wrong token is refused by the API.
