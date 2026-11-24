"""MCP server (FR-120, FR-121, RULE-004, RULE-005, RULE-010, AC-004, ADR-008) and
idempotency keys (API-Architecture).

The tools run through a real MCP client session against the real API app, with the MCP
token, so every rule is checked where it lives: in the API."""

import asyncio
import base64
import io
import json
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import CallToolResult, ImageContent, TextContent
from PIL import Image
from sqlalchemy.orm import Session

from asset_studio.modules.assets import service as assets
from asset_studio.modules.assets.models import AssetVersion
from asset_studio.modules.projects.config_schema import ProjectConfig
from asset_studio.modules.projects.service import create_project
from asset_studio.modules.storage.local import LocalStorage
from asset_studio_mcp.app import create_app
from asset_studio_mcp.client import Api
from asset_studio_mcp.server import build
from tests.conftest import MCP, ORIGIN, project_config

TOKEN = "test-mcp-token"
Call = Callable[[str, dict[str, Any]], Awaitable[CallToolResult]]


def _png() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (96, 96), (30, 60, 200)).save(out, "PNG")
    return out.getvalue()


def _mcp(client: TestClient, body: Callable[[Call], Awaitable[Any]], token: str = TOKEN) -> Any:
    """Run ``body(call)`` with an MCP client session on a server that calls the test API."""

    async def main() -> Any:
        transport = httpx.ASGITransport(app=client.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as http:
            server = build(lambda _ctx: Api(http, lambda: token))
            async with create_connected_server_and_client_session(server._mcp_server) as s:

                async def call(name: str, args: dict[str, Any]) -> CallToolResult:
                    return await s.call_tool(name, args)

                return await body(call)

    return asyncio.run(main())


def _text(r: CallToolResult) -> str:
    return " ".join(c.text for c in r.content if isinstance(c, TextContent))


def _data(r: CallToolResult) -> Any:
    assert not r.isError, _text(r)
    content = r.structuredContent
    if isinstance(content, dict):
        return content.get("result", content)
    return json.loads(_text(r))


def _project(db: Session) -> uuid.UUID:
    return create_project(db, ProjectConfig.model_validate(project_config()), "user").id


def _version(db: Session, storage: LocalStorage, pid: uuid.UUID) -> AssetVersion:
    asset = assets.create_asset(db, pid, category="core", name="Plank", actor="system")
    return assets.add_version(
        db, storage, asset.id, io.BytesIO(_png()), mime="image/png", actor="system"
    )


# --- the server surface -------------------------------------------------------------------------

DESIGNED = {
    "project_list",
    "project_get",
    "project_validate",
    "project_draft_create",
    "project_draft_update",
    "style_create",
    "style_get",
    "style_update",
    "reference_upload",
    "pose_list",
    "pose_detect",
    "workflow_list",
    "model_list",
    "engine_status",
    "generate_image",
    "generate_batch",
    "generation_status",
    "generation_cancel",
    "asset_list",
    "asset_get",
    "asset_validate",
    "asset_comment",
    "asset_approve",
    "asset_reject",
    "asset_publish",
}


def test_fr120_tools_match_the_design_and_hide_high_impact_operations() -> None:
    server = build(lambda _ctx: None)  # type: ignore[arg-type,return-value]
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert names >= DESIGNED
    forbidden = ("delete", "download", "licence", "setting", "backup", "restore", "shell", "path")
    assert not [n for n in names if any(word in n for word in forbidden)]


def test_http_needs_a_bearer_token_and_a_loopback_host() -> None:
    app = create_app(httpx.AsyncClient(base_url="http://api.invalid"))
    message = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/json, text/event-stream",
    }
    with TestClient(app, base_url="http://127.0.0.1:8411") as c:
        assert c.post("/mcp", json=message).status_code == 401
        r = c.post("/mcp", json=message, headers=headers)
        assert r.status_code == 200, r.text
        assert "asset_comment" in {t["name"] for t in r.json()["result"]["tools"]}
        r = c.post("/mcp", json=message, headers=headers | {"Host": "evil.example"})
        assert r.status_code in (400, 421)  # DNS rebinding protection


def test_a_wrong_token_is_refused_by_the_api(client: TestClient) -> None:
    async def body(call: Call) -> CallToolResult:
        return await call("project_list", {})

    r = _mcp(client, body, token="not-the-token")
    assert r.isError and "401" in _text(r)


# --- projects (FR-008, RULE-010) ----------------------------------------------------------------


def test_fr008_claude_drafts_a_project_and_only_the_user_confirms(client: TestClient) -> None:
    async def body(call: Call) -> str:
        bad = _data(await call("project_validate", {"config": {"name": "x"}}))
        assert bad["valid"] is False and bad["problems"]
        draft = _data(
            await call(
                "project_draft_create",
                {
                    "description": "Exercise illustrations",
                    "config": project_config(name="Exerzio"),
                    "assumptions": ["flat vector"],
                },
            )
        )
        changed = _data(
            await call(
                "project_draft_update", {"draft_id": draft["id"], "missing": ["brand colours"]}
            )
        )
        assert changed["missing"] == ["brand colours"]
        assert changed["created_by_actor"] == "mcp"
        return str(draft["id"])

    draft_id = _mcp(client, body)
    url = f"/api/v1/projects/drafts/{draft_id}/confirm"
    body_ = {"config": project_config()}
    assert client.post(url, json=body_, headers=MCP).json()["code"] == "ACTOR_NOT_ALLOWED"
    assert client.post(url, json=body_, headers=ORIGIN).status_code == 201


# --- review (FR-064, RULE-005, AC-004, FR-121) ---------------------------------------------


def test_ac004_claude_looks_and_comments_but_decides_only_when_allowed(
    client: TestClient, db: Session, storage: LocalStorage
) -> None:
    pid = _project(db)
    v = _version(db, storage, pid)
    assets.transition(db, v.id, "start_processing", "system")
    assets.transition(db, v.id, "processing_succeeded", "system")
    vid = str(v.id)

    async def refused(call: Call) -> CallToolResult:
        queue = _data(await call("review_queue", {"project_id": str(pid)}))
        assert [q["id"] for q in queue["items"]] == [vid]
        image = await call("asset_image", {"version_id": vid, "size": "thumb"})
        assert not image.isError and isinstance(image.content[0], ImageContent)
        _data(await call("asset_comment", {"version_id": vid, "body": "Elbows look right."}))
        return await call("asset_approve", {"version_id": vid})

    r = _mcp(client, refused)
    assert r.isError and "MCP_NOT_ALLOWED" in _text(r)  # a clear error (FR-121)
    comments = client.get(f"/api/v1/versions/{vid}/comments").json()
    assert [(c["actor"], c["body"]) for c in comments] == [("mcp", "Elbows look right.")]

    client.patch(f"/api/v1/projects/{pid}/settings", json={"mcp_can_decide": True}, headers=ORIGIN)

    async def allowed(call: Call) -> Any:
        return _data(await call("asset_reject", {"version_id": vid, "reason": "hands"}))

    assert _mcp(client, allowed)["state"] == "rejected"
    assert client.get(f"/api/v1/versions/{vid}").json()["history"][-1]["actor"] == "mcp"


def test_reference_upload_is_validated_like_any_upload(client: TestClient, db: Session) -> None:
    pid = str(_project(db))

    def args(data: str, name: str = "palette.png") -> dict[str, Any]:
        return {"project_id": pid, "role": "style", "name": name, "data_base64": data}

    async def body(call: Call) -> tuple[CallToolResult, ...]:
        ok = await call("reference_upload", args(base64.b64encode(_png()).decode()))
        bad = await call("reference_upload", args("%%%"))
        fake = await call("reference_upload", args(base64.b64encode(b"<svg onload=x>").decode()))
        return ok, bad, fake

    ok, bad, fake = _mcp(client, body)
    assert _data(ok)["role"] == "style"
    assert bad.isError and "BASE64_INVALID" in _text(bad)
    assert fake.isError and fake.content


# --- idempotency (API-Architecture) ---------------------------------------------------------------


def test_mcp_must_send_an_idempotency_key(client: TestClient, db: Session) -> None:
    pid = _project(db)
    spec = {
        "project_id": str(pid),
        "asset": {"category": "core", "name": "Plank"},
        "checkpoint_id": "sdxl-base-1.0",
        "prompt": "a plank",
    }
    r = client.post("/api/v1/generations", json=spec, headers=MCP)
    assert (r.status_code, r.json()["code"]) == (428, "IDEMPOTENCY_KEY_REQUIRED")


def test_idempotency_keys_replay_and_refuse_reuse(
    client: TestClient, db: Session, storage: LocalStorage
) -> None:
    pid = _project(db)
    v = _version(db, storage, pid)
    url = f"/api/v1/versions/{v.id}:process"
    key = {"Idempotency-Key": "process-plank-1"}
    first = client.post(url, headers=ORIGIN | key)
    assert first.status_code == 202, first.text
    again = client.post(url, headers=ORIGIN | key)
    assert again.status_code == 202 and again.json()["id"] == first.json()["id"]
    assert again.headers["Idempotent-Replay"] == "true"
    other = assets.add_version(
        db, storage, v.asset_id, io.BytesIO(_png()), mime="image/png", actor="system"
    )
    r = client.post(f"/api/v1/versions/{other.id}:process", headers=ORIGIN | key)
    assert r.json()["code"] == "IDEMPOTENCY_KEY_REUSED"
    r = client.post(url, headers=ORIGIN | {"Idempotency-Key": "short"})
    assert r.json()["code"] == "IDEMPOTENCY_KEY_INVALID"
    # Without a key the user's request runs as before.
    assert client.post(f"/api/v1/versions/{other.id}:process", headers=ORIGIN).status_code == 202


def test_pose_detect_through_mcp_repeats_nothing(client: TestClient, db: Session) -> None:
    pid = str(_project(db))

    async def body(call: Call) -> tuple[Any, ...]:
        ref = _data(
            await call(
                "reference_upload",
                {
                    "project_id": pid,
                    "role": "pose",
                    "name": "pose.png",
                    "data_base64": base64.b64encode(_png()).decode(),
                },
            )
        )
        args = {"reference_id": ref["id"], "request_id": "detect-pose-0001"}
        first = await call("pose_detect", args)
        again = await call("pose_detect", args)
        return first, again

    first, again = _mcp(client, body)
    if first.isError:  # pose models are optional in the test environment
        pytest.skip(_text(first))
    assert _data(first)["id"] == _data(again)["id"]


def test_workflow_list(client: TestClient) -> None:
    ids = {w["id"] for w in client.get("/api/v1/workflows").json()}
    assert {"txt2img", "img2img+pose+reference+vae", "remove_background"} <= ids
