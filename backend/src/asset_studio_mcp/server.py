"""MCP tools for Claude (FR-120, FR-121, MCP-Architecture).

Each tool is a thin call to the REST API with the caller's MCP token, so the API's rules hold
for Claude exactly as for any client:
- deciding (approve, reject, publish) only where the project allows it (RULE-005);
- never overwriting a published file (RULE-004);
- creating a project only from a draft the user confirms (RULE-010).

Not exposed at all: permanent delete, enabling ``mcp_can_decide``, model downloads, licence
acknowledgements, settings, backup and restore, any file path or shell.
"""

import uuid
from collections.abc import Callable
from typing import Any, Literal

from mcp.server.fastmcp import Context, FastMCP, Image
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings

from asset_studio_mcp.client import Api, ApiError, decode

Ctx = Context[Any, Any, Any]
MAX_REFERENCE = 20 * 1024 * 1024  # base64 uploads (MCP-Architecture)
MAX_IMAGE = 15 * 1024 * 1024  # what asset_image hands to Claude
JOB_FIELDS = (
    "id",
    "kind",
    "state",
    "progress",
    "wait_reason",
    "result",
    "error",
    "project_id",
    "created_at",
    "finished_at",
)
INSTRUCTIONS = """Asset Studio: a local workshop for consistent AI images.
Typical flow: project_list, project_get (categories and output), style_list, character_list,
pose_list, model_list(kind="checkpoint"), generate_check, generate_image (with a fresh
request_id), generation_status until the job is completed, asset_get, asset_image to look at a
version, then asset_comment with what you see. Approving, rejecting and publishing work only
where the user allowed it for the project; otherwise leave a comment for the user. New projects
are drafts (project_draft_create) that the user confirms in the app."""


def _id(value: str) -> str:
    try:
        return str(uuid.UUID(value))
    except ValueError as exc:
        raise ToolError(f"ID_INVALID: {value!r} is not an id.") from exc


def build(api_for: Callable[[Ctx], Api], *, host: str = "127.0.0.1", port: int = 8411) -> FastMCP:
    """The MCP server. ``api_for(ctx)`` returns the API client acting for the caller."""
    mcp = FastMCP(
        "asset-studio",
        instructions=INSTRUCTIONS,
        host=host,
        port=port,
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*"],
            allowed_origins=["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"],
        ),
    )

    # --- projects (FR-008, RULE-010) -----------------------------------------------------------

    @mcp.tool()
    async def project_list(ctx: Ctx, include_archived: bool = False) -> Any:
        """List projects with their id, name, type and whether Claude may decide."""
        return await api_for(ctx).get("/projects", include_archived=include_archived)

    @mcp.tool()
    async def project_get(ctx: Ctx, project_id: str) -> Any:
        """A project with its configuration: categories, output size and format, naming."""
        return await api_for(ctx).get(f"/projects/{_id(project_id)}")

    @mcp.tool()
    async def project_validate(ctx: Ctx, config: dict[str, Any]) -> Any:
        """Check a project configuration against the schema without saving it."""
        return await api_for(ctx).post("/projects:validate", {"config": config})

    @mcp.tool()
    async def project_draft_create(
        ctx: Ctx,
        description: str,
        config: dict[str, Any],
        assumptions: list[str] | None = None,
        missing: list[str] | None = None,
    ) -> Any:
        """Propose a new project. It stays a draft until the user confirms it in the app.
        List what you assumed and what is still missing."""
        body = {
            "description": description,
            "config": config,
            "assumptions": assumptions or [],
            "missing": missing or [],
        }
        return await api_for(ctx).post("/projects/drafts", body)

    @mcp.tool()
    async def project_draft_update(
        ctx: Ctx,
        draft_id: str,
        description: str | None = None,
        config: dict[str, Any] | None = None,
        assumptions: list[str] | None = None,
        missing: list[str] | None = None,
    ) -> Any:
        """Revise a pending project draft you created."""
        fields = {
            "description": description,
            "config": config,
            "assumptions": assumptions,
            "missing": missing,
        }
        body = {k: v for k, v in fields.items() if v is not None}
        return await api_for(ctx).request("PUT", f"/projects/drafts/{_id(draft_id)}", json=body)

    # --- styles, characters, references, poses -------------------------------------------------

    @mcp.tool()
    async def style_list(ctx: Ctx, project_id: str) -> Any:
        """The project's styles (attributes such as palette, line, shading, avoid list)."""
        return await api_for(ctx).get(f"/projects/{_id(project_id)}/styles")

    @mcp.tool()
    async def style_get(ctx: Ctx, style_id: str) -> Any:
        """One style with all its attributes and its version."""
        return await api_for(ctx).get(f"/styles/{_id(style_id)}")

    @mcp.tool()
    async def style_create(ctx: Ctx, project_id: str, name: str, attributes: dict[str, Any]) -> Any:
        """Create a style. Every change is recorded as a new style version."""
        body = {"name": name, "attributes": attributes}
        return await api_for(ctx).post(f"/projects/{_id(project_id)}/styles", body)

    @mcp.tool()
    async def style_update(
        ctx: Ctx,
        style_id: str,
        name: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> Any:
        """Change a style's name or attributes (a new style version)."""
        body = {k: v for k, v in {"name": name, "attributes": attributes}.items() if v is not None}
        return await api_for(ctx).request("PATCH", f"/styles/{_id(style_id)}", json=body)

    @mcp.tool()
    async def character_list(ctx: Ctx, project_id: str) -> Any:
        """The project's characters (description and attributes)."""
        return await api_for(ctx).get(f"/projects/{_id(project_id)}/characters")

    @mcp.tool()
    async def reference_upload(
        ctx: Ctx,
        project_id: str,
        role: Literal[
            "style",
            "character",
            "pose",
            "composition",
            "colour",
            "anatomy",
            "equipment",
            "background",
            "other",
        ],
        name: str,
        data_base64: str,
    ) -> Any:
        """Upload a reference image (PNG, JPEG or WebP, at most 20 MB, base64). It is checked
        like any upload."""
        data = decode(data_base64, MAX_REFERENCE)
        return await api_for(ctx).request(
            "POST",
            f"/projects/{_id(project_id)}/references",
            params={"role": role, "name": name},
            content=data,
        )

    @mcp.tool()
    async def pose_list(ctx: Ctx, project_id: str | None = None, view: str | None = None) -> Any:
        """Poses: the built-in ones and the project's own, optionally by view."""
        return await api_for(ctx).get("/poses", project_id=project_id, view=view)

    @mcp.tool()
    async def pose_detect(ctx: Ctx, reference_id: str, request_id: str) -> Any:
        """Detect a pose skeleton in a reference image. Returns a job; the user saves the
        proposed skeleton. ``request_id``: a fresh unique id, reused only to retry this call."""
        return await api_for(ctx).post(
            "/poses:detect", {"reference_id": _id(reference_id)}, idempotency_key=request_id
        )

    # --- engine, models, workflows ---------------------------------------------------------------

    @mcp.tool()
    async def engine_status(ctx: Ctx) -> Any:
        """Whether the generation engine runs. While it is stopped, generation jobs wait in the
        queue; only the user can start it."""
        return await api_for(ctx).get("/system/engine")

    @mcp.tool()
    async def model_list(ctx: Ctx, kind: str | None = None, project_id: str | None = None) -> Any:
        """Installed and available models (checkpoint, lora, controlnet, ...). With a project,
        each model says whether its licence conflicts with the project's intended use."""
        return await api_for(ctx).get("/models", kind=kind, project_id=project_id)

    @mcp.tool()
    async def workflow_list(ctx: Ctx) -> Any:
        """The built-in workflows. Generation picks one from the request's inputs."""
        return await api_for(ctx).get("/workflows")

    # --- generation (FR-030-FR-038) --------------------------------------------------------------

    def spec(
        project_id: str,
        checkpoint_id: str,
        prompt: str,
        asset: dict[str, Any],
        options: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return {
            **(options or {}),
            "project_id": _id(project_id),
            "checkpoint_id": checkpoint_id,
            "prompt": prompt,
            "asset": asset,
        }

    def target(asset_id: str | None, category: str | None, name: str | None) -> dict[str, Any]:
        if asset_id:
            return {"asset_id": _id(asset_id)}
        if not category or not name:
            raise ToolError(
                "Give asset_id for a new version, or category and name for a new asset."
            )
        return {"category": category, "name": name}

    @mcp.tool()
    async def generate_check(
        ctx: Ctx,
        project_id: str,
        checkpoint_id: str,
        prompt: str,
        asset_id: str | None = None,
        category: str | None = None,
        name: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> Any:
        """Check a generation request before queueing: problems, licences the user must
        confirm, the workflow and models, the final prompts. ``options`` may hold style_id,
        character_id, pose_id, pose_strength, reference, init, negative, seed, steps, cfg,
        sampler, scheduler, width, height, variants and batch."""
        body = spec(project_id, checkpoint_id, prompt, target(asset_id, category, name), options)
        return await api_for(ctx).post("/generations:check", body)

    @mcp.tool()
    async def generate_image(
        ctx: Ctx,
        project_id: str,
        checkpoint_id: str,
        prompt: str,
        request_id: str,
        asset_id: str | None = None,
        category: str | None = None,
        name: str | None = None,
        variants: int = 1,
        options: dict[str, Any] | None = None,
    ) -> Any:
        """Queue image generation: a new asset (category and name) or a new version of an
        existing asset (asset_id). Returns jobs; follow them with generation_status.
        ``request_id``: a fresh unique id (e.g. a UUID); repeating it repeats nothing."""
        body = spec(project_id, checkpoint_id, prompt, target(asset_id, category, name), options)
        body["variants"] = variants
        return await api_for(ctx).post("/generations", body, idempotency_key=request_id)

    @mcp.tool()
    async def generate_batch(
        ctx: Ctx,
        project_id: str,
        checkpoint_id: str,
        category: str,
        items: list[dict[str, str]],
        request_id: str,
        prompt: str = "",
        options: dict[str, Any] | None = None,
    ) -> Any:
        """Queue one new asset per item ({"name": ..., "prompt": ...}); ``prompt`` is added to
        every item. ``request_id``: a fresh unique id for this batch."""
        body = spec(
            project_id, checkpoint_id, prompt, {"category": category, "name": "batch"}, options
        )
        body["batch"] = items
        return await api_for(ctx).post("/generations", body, idempotency_key=request_id)

    @mcp.tool()
    async def generation_status(ctx: Ctx, job_id: str) -> Any:
        """A job's state (queued, running, completed, failed, cancelled), progress, why it
        waits, its result (asset and version ids) or its error."""
        job = await api_for(ctx).get(f"/jobs/{_id(job_id)}")
        return {k: job.get(k) for k in JOB_FIELDS}

    @mcp.tool()
    async def generation_cancel(ctx: Ctx, job_id: str) -> Any:
        """Cancel a queued or running job."""
        job = await api_for(ctx).post(f"/jobs/{_id(job_id)}/cancel")
        return {k: job.get(k) for k in JOB_FIELDS}

    # --- assets and review (FR-050, FR-060-FR-064) -----------------------------------------------

    @mcp.tool()
    async def asset_list(
        ctx: Ctx, project_id: str, state: str | None = None, q: str | None = None, limit: int = 50
    ) -> Any:
        """Assets of a project with their newest version; filter by a version state
        (awaiting_review, approved, ...) or by text."""
        return await api_for(ctx).get(
            "/assets", project_id=_id(project_id), state=state, q=q, limit=max(1, min(limit, 200))
        )

    @mcp.tool()
    async def review_queue(ctx: Ctx, project_id: str) -> Any:
        """Versions waiting for review, oldest first."""
        return await api_for(ctx).get(
            "/versions", project_id=_id(project_id), state="awaiting_review"
        )

    @mcp.tool()
    async def asset_get(ctx: Ctx, asset_id: str) -> Any:
        """An asset with all its versions, their states and generation parameters."""
        return await api_for(ctx).get(f"/assets/{_id(asset_id)}")

    @mcp.tool()
    async def asset_image(
        ctx: Ctx, version_id: str, size: Literal["preview", "thumb"] = "preview"
    ) -> Image:
        """Look at a version: its preview (1024 px) or thumbnail (256 px). A version that is
        not processed yet is shown from its original file."""
        path = f"/versions/{_id(version_id)}/file"
        try:
            data, mime = await api_for(ctx).file(path, MAX_IMAGE, size=size)
        except ApiError as exc:
            if exc.code != "FILE_NOT_AVAILABLE":
                raise
            data, mime = await api_for(ctx).file(path, MAX_IMAGE, size="original")
        return Image(data=data, format=mime.split("/")[-1].split(";")[0])

    @mcp.tool()
    async def asset_validate(ctx: Ctx, version_id: str) -> Any:
        """The newest technical validation of a version (size, format, background, naming,
        integrity). Informative only."""
        return await api_for(ctx).get(f"/versions/{_id(version_id)}/validation")

    @mcp.tool()
    async def asset_comment(ctx: Ctx, version_id: str, body: str) -> Any:
        """Comment on a version for the user. Always allowed."""
        return await api_for(ctx).post(f"/versions/{_id(version_id)}/comments", {"body": body})

    @mcp.tool()
    async def asset_approve(ctx: Ctx, version_id: str) -> Any:
        """Approve a version waiting for review. Refused unless the project lets Claude decide
        (RULE-005); then leave a comment instead."""
        return await api_for(ctx).post(
            f"/versions/{_id(version_id)}/transitions", {"action": "approve"}
        )

    @mcp.tool()
    async def asset_reject(ctx: Ctx, version_id: str, reason: str = "") -> Any:
        """Reject a version waiting for review, with a reason. Refused unless the project lets
        Claude decide (RULE-005)."""
        return await api_for(ctx).post(
            f"/versions/{_id(version_id)}/transitions", {"action": "reject", "reason": reason}
        )

    # --- publishing (FR-092-FR-095) --------------------------------------------------------------

    @mcp.tool()
    async def publish_options(ctx: Ctx, project_id: str) -> Any:
        """The project's export presets and target folders, for asset_publish."""
        pid = _id(project_id)
        return {
            "presets": await api_for(ctx).get(f"/projects/{pid}/presets"),
            "targets": await api_for(ctx).get(f"/projects/{pid}/targets"),
        }

    @mcp.tool()
    async def asset_publish(
        ctx: Ctx,
        project_id: str,
        preset_id: str,
        target_id: str,
        version_ids: list[str],
        request_id: str,
    ) -> Any:
        """Publish approved versions to a target through a preset. Only where the project lets
        Claude decide (RULE-005), and never over existing files (RULE-004): if any file exists,
        nothing is published and the user has to do it in the app."""
        plan = await api_for(ctx).post(
            "/publications:plan",
            {
                "project_id": _id(project_id),
                "preset_id": _id(preset_id),
                "target_id": _id(target_id),
                "version_ids": [_id(v) for v in version_ids],
            },
        )
        if plan["overwrites"]:
            raise ToolError(
                "MCP_OVERWRITE_NOT_ALLOWED: these files already exist and only the user can "
                f"overwrite them: {plan['overwrites'][:20]}"
            )
        job = await api_for(ctx).post(
            "/publications", {"plan_id": plan["id"]}, idempotency_key=request_id
        )
        return {
            "job_id": job["id"],
            "files": [f["path"] for item in plan["items"] for f in item["files"]],
            "skipped": plan["skipped"],
        }

    return mcp
